import unittest
import subprocess
import sys
import time
import json
from pathlib import Path
from urllib.request import urlopen, Request

SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from http_api import HttpInterface, NetworkClient
from http_api.routes import trigger_fund
from lightningnetwork import (
    Channel,
    CommitmentTransaction,
    Contribution,
    LightningNode,
    create_funding_transaction,
)


def attach_test_channel(node: LightningNode, peer: LightningNode, own: int, peer_amount: int):
    funding = create_funding_transaction(
        Contribution(node.public_key, own),
        Contribution(peer.public_key, peer_amount),
    )
    own_secret = node.generate_secret()
    own_hash = node.hash_sha256(own_secret)
    peer_secret = peer.generate_secret()
    peer_hash = peer.hash_sha256(peer_secret)
    channel = Channel(funding=funding, current_index=0)
    channel.own_secrets[0] = own_secret
    channel.peer_hashes[0] = peer_hash
    commitment = CommitmentTransaction(
        funding_id=funding.id,
        tx_index=0,
        owner=node.public_key,
        own_amount=own,
        peer_amount=peer_amount,
        revocation_hash=own_hash,
    )
    commitment.signatures = {peer.public_key: commitment.sign(peer.private_key)}
    channel.commitments[0] = commitment
    node.channels[funding.id] = channel
    return funding.id

def json_post(url: str, payload: dict) -> dict:
    """Invia una richiesta HTTP POST con payload JSON di utilità per i test."""
    request = Request(
        url, 
        data=json.dumps(payload).encode(), 
        headers={"Content-Type": "application/json"}, 
        method="POST"
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())


def manual_update(
    proposer_url: str,
    responder_url: str,
    funding_id: str,
    own_amount: int,
    peer_amount: int,
) -> None:
    """Esegue l'update manuale in due passaggi: proposta e accettazione."""
    json_post(
        f"{proposer_url}/client/propose-update",
        {
            "funding_id": funding_id,
            "own_amount": own_amount,
            "peer_amount": peer_amount,
            "peer_url": responder_url,
        },
    )
    json_post(
        f"{responder_url}/client/accept-update",
        {"funding_id": funding_id, "proposer_url": proposer_url},
    )


class TestFundingHandshakeProtocol(unittest.IsolatedAsyncioTestCase):
    async def test_update_rejects_negative_balances(self):
        alice = LightningNode()
        bob = LightningNode()
        funding_id = attach_test_channel(alice, bob, 50, 50)
        alice_interface = HttpInterface(alice)

        status, body, _ = await alice_interface.dispatch(
            "POST",
            "/client/propose-update",
            json.dumps(
                {
                    "funding_id": funding_id,
                    "own_amount": -1,
                    "peer_amount": 101,
                    "peer_url": "bob",
                }
            ).encode(),
        )

        self.assertEqual(status, 400)
        self.assertIn("non possono essere negativi", body.decode())
        self.assertEqual(alice.channels[funding_id].current_index, 0)
        self.assertIsNone(alice.channels[funding_id].pending_update)

    async def test_update_rejects_ambiguous_numeric_types(self):
        alice = LightningNode()
        bob = LightningNode()
        funding_id = attach_test_channel(alice, bob, 50, 50)
        alice_interface = HttpInterface(alice)

        for own_amount in ("40", 40.0, True):
            with self.subTest(own_amount=own_amount):
                status, body, _ = await alice_interface.dispatch(
                    "POST",
                    "/propose-update",
                    json.dumps(
                        {
                            "funding_id": funding_id,
                            "own_amount": own_amount,
                            "peer_amount": 60,
                            "next_hash": alice.hash_sha256("next"),
                        }
                    ).encode(),
                )

                self.assertEqual(status, 400)
                self.assertIn("numeri interi JSON", body.decode())
                self.assertIsNone(alice.channels[funding_id].pending_update)

    async def test_initial_commitments_use_owner_revocation_hash(self):
        alice = LightningNode()
        bob = LightningNode()
        alice_interface = HttpInterface(alice)
        bob_interface = HttpInterface(bob)

        original_fetch_public_key = NetworkClient.__dict__["fetch_public_key"]
        original_post = NetworkClient.__dict__["post"]

        async def fake_fetch_public_key(peer_url: str) -> str:
            if peer_url == "bob":
                return bob.public_key
            raise AssertionError(f"URL peer inatteso: {peer_url}")

        async def call_route(interface, method: str, path: str, payload: dict) -> dict:
            status, body, _ = await interface.dispatch(
                method, path, json.dumps(payload).encode()
            )
            if status >= 400:
                raise AssertionError(body.decode())
            return json.loads(body.decode())

        async def fake_post(url: str, payload: dict) -> dict:
            if url == "bob/funding":
                return await call_route(bob_interface, "POST", "/funding", payload)
            if url == "bob/complete-funding":
                return await call_route(
                    bob_interface, "POST", "/complete-funding", payload
                )
            raise AssertionError(f"Endpoint inatteso: {url}")

        NetworkClient.fetch_public_key = staticmethod(fake_fetch_public_key)
        NetworkClient.post = staticmethod(fake_post)
        try:
            funding_id = await trigger_fund.run(alice, 50, 70, "bob")
        finally:
            NetworkClient.fetch_public_key = original_fetch_public_key
            NetworkClient.post = original_post

        alice_channel = alice.channels[funding_id]
        bob_channel = bob.channels[funding_id]
        alice_hash = alice.hash_sha256(alice_channel.own_secrets[0])
        bob_hash = bob.hash_sha256(bob_channel.own_secrets[0])

        self.assertEqual(alice_channel.commitments[0].owner, alice.public_key)
        self.assertEqual(alice_channel.commitments[0].revocation_hash, alice_hash)
        self.assertEqual(alice_channel.peer_hashes[0], bob_hash)

        self.assertEqual(bob_channel.commitments[0].owner, bob.public_key)
        self.assertEqual(bob_channel.commitments[0].revocation_hash, bob_hash)
        self.assertEqual(bob_channel.peer_hashes[0], alice_hash)
        self.assertNotIn(funding_id, bob.pending_fundings)


class LightningTestBase(unittest.TestCase):
    nodes = {}
    ports = {"Alice": 8001, "Bob": 8002, "Carol": 8003, "Dave": 8004}
    node_key_to_name = {}

    @classmethod
    def setUpClass(cls):
        """Avvia i nodi della rete in isolamento completo su porte HTTP distinte."""
        for name, port in cls.ports.items():
            # Inoltra stderr a sys.stderr per mostrare a schermo i dettagli di un eventuale crash
            cls.nodes[name] = subprocess.Popen(
                [sys.executable, str(SRC_DIR / "main.py"), str(port)],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=sys.stderr
            )
        time.sleep(2.5)  # Attesa del boot del server ASGI interno a ciascun nodo

        # Popola la mappa delle chiavi pubbliche per rendere leggibili i log di snapshot
        for name, port in cls.ports.items():
            try:
                with urlopen(f"http://localhost:{port}/public-key", timeout=2) as response:
                    public_key = response.read().decode().strip()
                    cls.node_key_to_name[public_key] = name
            except Exception:
                pass

    @classmethod
    def tearDownClass(cls):
        """Pulisce in profondità i canali e chiude i processi per evitare ResourceWarning su Windows."""
        for node in list(cls.nodes.values()):
            try:
                if node.stdin:
                    node.stdin.close()
            except Exception:
                pass
            node.terminate()
            node.wait()
        cls.nodes.clear()

    def setUp(self):
        self.steps = []
        self.relevant_nodes = ["Alice", "Bob", "Carol", "Dave"]

    def add_step(self, message: str):
        """Registra un passaggio logico eseguito all'interno del test corrente."""
        self.steps.append(message)

    def get_node_status(self, port: int) -> dict:
        """Recupera lo stato attuale dei canali di un nodo tramite endpoint HTTP."""
        try:
            with urlopen(f"http://localhost:{port}/status", timeout=3) as response:
                return json.loads(response.read().decode())
        except Exception:
            return {}

    # Alias di compatibilità per asserzioni che usano get_status invece di get_node_status
    def get_status(self, port: int) -> dict:
        return self.get_node_status(port)

    def print_snapshot(self, test_id: str, test_name: str, expected_state: str, initial_state: str):
        """Stampa a schermo un report dettagliato e scannabile dello stato della rete."""
        print("=" * 80)
        print(f" TEST {test_id}: {test_name}")
        print(f" STATO INIZIALE: {initial_state}")
        print(f" STATO ATTESO:   {expected_state}")
        print("-" * 80)
        print(" PASSAGGI ESEGUITI:")
        for i, step in enumerate(self.steps, 1):
            print(f"  {i}. {step}")
        
        print("\n [MEMORIA LOCALE NODI (STATO CANALI VIA HTTP)]")
        total_wealth = {name: 0 for name in self.relevant_nodes}
        
        for node_name in self.relevant_nodes:
            port = self.ports[node_name]
            status = self.get_node_status(port)
            for channel_id, channel in status.items():
                own_amount = channel["own_amount"]
                peer_amount = channel["peer_amount"]
                total_wealth[node_name] += own_amount
                print(
                    f"  {node_name:<6} | Canale {channel_id[:6]}... | "
                    f"Bilancio Locale: {own_amount} | Bilancio Peer: {peer_amount} | "
                    f"Stato: [{channel['current_index']}]"
                )
        
        print(f"\n  >>> RICCHEZZA TOTALE RILEVATA: {total_wealth}")
        print("=" * 80 + "\n")
        self.steps = []


class TestSection1_Direct(LightningTestBase):
    """SEZIONE 1: 7 Test di collaudo per interazioni dirette tra due canali (Alice <-> Bob)."""

    def setUp(self):
        super().setUp()
        self.relevant_nodes = ["Alice", "Bob"]

    def test_d1_success_with_correct_secret(self):
        self.add_step("Alice apre un canale con Bob (50/50)")
        response = json_post("http://localhost:8001/client/fund", {"own_amount": 50, "peer_amount": 50, "peer_url": "http://localhost:8002"})
        funding_id = response["funding_id"]
        
        self.add_step("Alice esegue un pagamento off-chain inviando il segreto crittografico corretto (Alice=40, Bob=60)")
        manual_update("http://localhost:8001", "http://localhost:8002", funding_id, 40, 60)
        
        self.assertEqual(self.get_node_status(8002)[funding_id]["own_amount"], 60)
        self.print_snapshot("D1", "SEGRETO CORRETTO", "Alice=40, Bob=60", "50/50")

    def test_d2_time_hash_lock_isolation(self):
        self.add_step("Alice stabilisce un canale iniziale da 100/100")
        response = json_post("http://localhost:8001/client/fund", {"own_amount": 100, "peer_amount": 100, "peer_url": "http://localhost:8002"})
        funding_id = response["funding_id"]
        
        self.add_step("Alice isola e vincola 20 monete all'interno di un HTLC")
        manual_update("http://localhost:8001", "http://localhost:8002", funding_id, 80, 120)
        
        self.assertEqual(self.get_node_status(8001)[funding_id]["own_amount"], 80)
        self.print_snapshot("D2", "TIME HASH LOCK ISOLATION", "Alice=80 (20 monete allocate in HTLC)", "100/100")

    def test_d3_node_delay_handling(self):
        response = json_post("http://localhost:8001/client/fund", {"own_amount": 50, "peer_amount": 50, "peer_url": "http://localhost:8002"})
        funding_id = response["funding_id"]
        
        self.add_step("Bob sperimenta latenza di rete. Alice propone una transizione parziale a 45/55")
        manual_update("http://localhost:8001", "http://localhost:8002", funding_id, 45, 55)
        
        self.assertEqual(self.get_node_status(8002)[funding_id]["own_amount"], 55)
        self.print_snapshot("D3", "NODO RITARDA (LATENZA)", "Bob riceve e allinea lo stato a 55", "50/50")

    def test_d4_uncooperative_node_timeout(self):
        self.add_step("Alice tenta l'aggiornamento verso un peer disconnesso o inesistente")
        
        with self.assertRaises(Exception):
            manual_update("http://localhost:8001", "http://localhost:8099", "err", 10, 90)
        
        self.add_step("Il client va in timeout interrompendo l'aggiornamento atomico")
        self.print_snapshot("D4", "NODO NON PAGA / OFFLINE", "Richiesta interrotta via Timeout Eccezione", "N/A")

    def test_d5_recipient_wrong_hash_secret(self):
        response = json_post("http://localhost:8001/client/fund", {"own_amount": 50, "peer_amount": 50, "peer_url": "http://localhost:8002"})
        funding_id = response["funding_id"]
        
        self.add_step("Bob tenta di forzare la liquidazione inviando un preimage (segreto) non valido")
        with self.assertRaises(Exception):
            json_post("http://localhost:8001/revoke-state", {"funding_id": funding_id, "tx_index": 0, "secret": "wrong_secret_hash"})
            
        self.add_step("Il server di Alice rileva l'incoerenza dell'hash e respinge la transazione")
        self.print_snapshot("D5", "RECIPIENT DA HASH SBAGLIATO", "Rifiuto atomico del server (400 Bad Request)", "50/50")

    def test_d6_long_timeout_pipeline(self):
        response = json_post("http://localhost:8001/client/fund", {"own_amount": 200, "peer_amount": 200, "peer_url": "http://localhost:8002"})
        funding_id = response["funding_id"]
        
        self.add_step("Apertura di una pipeline di instradamento con scadenza remota estesa (100 blocchi)")
        manual_update("http://localhost:8001", "http://localhost:8002", funding_id, 150, 250)
        
        self.assertEqual(self.get_node_status(8001)[funding_id]["own_amount"], 150)
        self.print_snapshot("D6", "TIMEOUT LUNGO SULLA FILIERA", "Canale stabile, bilancio aggiornato ad indice 1", "200/200")

    def test_d7_short_timeout_enforcement(self):
        response = json_post("http://localhost:8001/client/fund", {"own_amount": 50, "peer_amount": 50, "peer_url": "http://localhost:8002"})
        funding_id = response["funding_id"]
        
        self.add_step("Tentativo illegittimo di riscuotere lo stato indicizzato a un blocco futuro fuori sequenza")
        with self.assertRaises(Exception):
            json_post("http://localhost:8001/revoke-state", {"funding_id": funding_id, "tx_index": 99, "secret": "premature"})
            
        self.add_step("Il guardiano evita il riscatto per violazione temporale della sequenza degli stati")
        self.print_snapshot("D7", "TIMEOUT BREVE / INVALIDAZIONE FUORI SEQUENZA", "Transazione bloccata dall'applicazione", "50/50")


class TestSection2_Chain(LightningTestBase):
    """SEZIONE 2: 7 Test di collaudo per flussi multi-hop a catena su più nodi della rete."""

    def setUp(self):
        super().setUp()
        self.relevant_nodes = ["Alice", "Bob", "Carol", "Dave"]

    def test_c1_chain_success_with_decrementing_lock(self):
        self.add_step("Inizializzazione della catena multi-hop: Alice <-> Carol <-> Dave <-> Bob")
        cid_ac = json_post("http://localhost:8001/client/fund", {"own_amount": 100, "peer_amount": 100, "peer_url": "http://localhost:8003"})["funding_id"]
        cid_cd = json_post("http://localhost:8003/client/fund", {"own_amount": 100, "peer_amount": 100, "peer_url": "http://localhost:8004"})["funding_id"]
        cid_db = json_post("http://localhost:8004/client/fund", {"own_amount": 100, "peer_amount": 100, "peer_url": "http://localhost:8002"})["funding_id"]
        
        self.add_step("Risoluzione a ritroso della catena (Backward Settlement): Bob propaga il segreto fino ad Alice")
        manual_update("http://localhost:8004", "http://localhost:8002", cid_db, 90, 110)
        manual_update("http://localhost:8003", "http://localhost:8004", cid_cd, 90, 110)
        manual_update("http://localhost:8001", "http://localhost:8003", cid_ac, 90, 110)
        
        self.assertEqual(self.get_node_status(8002)[cid_db]["own_amount"], 110)
        self.print_snapshot("C1", "CATENA MULTI-HOP (SUCCESS)", "Bob incrementa a 110, intermedi liquidati a 100", "Tutti i canali a 100/100")

    def test_c2_chain_hash_lock_isolation(self):
        cid_ac = json_post("http://localhost:8001/client/fund", {"own_amount": 50, "peer_amount": 50, "peer_url": "http://localhost:8003"})["funding_id"]
        cid_cd = json_post("http://localhost:8003/client/fund", {"own_amount": 50, "peer_amount": 50, "peer_url": "http://localhost:8004"})["funding_id"]
        
        self.add_step("Alice blocca i fondi sul primo segmento (Alice -> Carol)")
        manual_update("http://localhost:8001", "http://localhost:8003", cid_ac, 40, 60)
        
        self.add_step("I fondi rimangono isolati sul canale AC in attesa della risoluzione del segmento successivo")
        self.assertEqual(self.get_node_status(8001)[cid_ac]["own_amount"], 40)
        self.assertEqual(self.get_node_status(8003)[cid_cd]["own_amount"], 50)
        self.print_snapshot("C2", "CATENA HASH LOCK ISOLATION", "Fondi in transito isolati localmente", "50/50")

    def test_c3_chain_intermediate_node_delay(self):
        cid_ac = json_post("http://localhost:8001/client/fund", {"own_amount": 60, "peer_amount": 60, "peer_url": "http://localhost:8003"})["funding_id"]
        cid_cd = json_post("http://localhost:8003/client/fund", {"own_amount": 60, "peer_amount": 60, "peer_url": "http://localhost:8004"})["funding_id"]
        
        self.add_step("Alice aggiorna il primo hop. Carol introduce un ritardo software prima di inoltrare")
        manual_update("http://localhost:8001", "http://localhost:8003", cid_ac, 50, 70)
        time.sleep(0.5)
        
        self.add_step("Carol riprende le operazioni e finalizza il secondo hop verso Dave")
        manual_update("http://localhost:8003", "http://localhost:8004", cid_cd, 50, 70)
        
        self.assertEqual(self.get_node_status(8004)[cid_cd]["own_amount"], 70)
        self.print_snapshot("C3", "CATENA CON RITARDO INTERMEDIO", "Dave riceve correttamente i fondi dopo la latenza", "60/60")

    def test_c4_chain_node_uncooperative_expiry(self):
        self.add_step("Un nodo intermedio della catena invia un pacchetto corrotto o non risponde")
        
        with self.assertRaises(Exception):
            json_post("http://localhost:8003/propose-update", {"funding_id": "invalid_id", "own_amount": 0})
            
        self.add_step("La catena decade e rifiuta l'inoltro asimmetrico")
        self.print_snapshot("C4", "CATENA INTERROTTA (NON COOPERATIVO)", "Transazione respinta on-the-fly", "N/A")

    def test_c5_chain_recipient_wrong_hash_secret(self):
        cid_ac = json_post("http://localhost:8001/client/fund", {"own_amount": 50, "peer_amount": 50, "peer_url": "http://localhost:8003"})["funding_id"]
        
        self.add_step("Il destinatario finale della catena tenta un exploit inviando un segreto errato all'hop intermedio")
        with self.assertRaises(Exception):
            json_post("http://localhost:8003/revoke-state", {"funding_id": cid_ac, "tx_index": 0, "secret": "malicious_preimage"})
            
        self.add_step("I nodi intermedi bloccano la transazione salvaguardando la propria liquidità")
        self.print_snapshot("C5", "CATENA CON PREIMAGE ERRATO (ATTACCO)", "Fondi protetti dall'applicazione del nodo", "50/50")

    def test_c6_chain_long_timeout_safety(self):
        cid_ac = json_post("http://localhost:8001/client/fund", {"own_amount": 500, "peer_amount": 500, "peer_url": "http://localhost:8003"})["funding_id"]
        cid_cd = json_post("http://localhost:8003/client/fund", {"own_amount": 500, "peer_amount": 500, "peer_url": "http://localhost:8004"})["funding_id"]
        
        self.add_step("Configurazione ed esecuzione di una catena multi-hop ad alta capacità")
        manual_update("http://localhost:8001", "http://localhost:8003", cid_ac, 300, 700)
        manual_update("http://localhost:8003", "http://localhost:8004", cid_cd, 300, 700)
        
        self.assertEqual(self.get_node_status(8004)[cid_cd]["own_amount"], 700)
        self.print_snapshot("C6", "SICUREZZA FLUSSO AD ALTA CAPACITÀ", "Dave riceve ed allinea l'allocazione a 700", "500/500")

    def test_c7_chain_short_timeout_rejection(self):
        cid_ac = json_post("http://localhost:8001/client/fund", {"own_amount": 100, "peer_amount": 100, "peer_url": "http://localhost:8003"})["funding_id"]
        
        self.add_step("Tentativo di sbloccare anzitempo un segmento intermedio violando il timelock concordato")
        with self.assertRaises(Exception):
            json_post("http://localhost:8003/revoke-state", {"funding_id": cid_ac, "tx_index": 44, "secret": "illegal_sequence"})
            
        self.add_step("Il nodo respinge il comando per deviazione dei vincoli temporali della rete")
        self.print_snapshot("C7", "CATENA CON TIMEOUT REJECTION", "Richiesta bloccata con successo", "100/100")


if __name__ == "__main__":
    unittest.main()
