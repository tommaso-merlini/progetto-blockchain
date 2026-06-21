import unittest
from blockchain import BlockChain
from actors import Actor
from domain_types import HTLC

class LightningTestBase(unittest.TestCase):
    def setUp(self):
        self.bc = BlockChain(verbose=True)
        self.alice = Actor("Alice", verbose=True)
        self.carol = Actor("Carol", verbose=True)
        self.dave = Actor("Dave", verbose=True)
        self.bob = Actor("Bob", verbose=True)
        
        self.all_nodes = [self.alice, self.carol, self.dave, self.bob]
        self.name_map = {n.pub_key: n.id for n in self.all_nodes}
        self.relevant_nodes = self.all_nodes
        self.steps = []
        self.claims_success = [] 
        self.claims_timeout = [] 

    def add_step(self, msg):
        self.steps.append(msg)

    def get_current_wealth(self):
        """Calcola la ricchezza totale di ogni nodo sommando i canali in memoria."""
        wealth = {n.id: 0 for n in self.relevant_nodes}
        for n in self.relevant_nodes:
            for state in n.channels.values():
                if state.commitments:
                    wealth[n.id] += state.commitments[-1].balances[n.pub_key]
        return wealth

    def get_final_chain_balances(self, addr):
        """Recupera il bilancio finale calcolato sulla blockchain per un contratto."""
        ms = self.bc.addresses[addr]
        if ms.settlement:
            return {self.name_map.get(pk, pk[:8]): amt for pk, amt in ms.settlement.items()}
        if ms.pending_close:
            pc = ms.pending_close
            view = {self.name_map.get(pk, pk[:8]): amt for pk, amt in pc.balances.items()}
            for h in pc.htlcs:
                if h.resolved:
                    winner_pk = h.receiver if h.id in self.claims_success else h.sender
                    winner_name = self.name_map.get(winner_pk)
                    view[winner_name] = view.get(winner_name, 0) + h.amount
            return view
        return {self.name_map.get(pk, pk[:8]): amt for pk in ms.public_keys for amt in [0]} # Fallback

    def print_snapshot(self, test_id, name, expected, initial):
        print("=" * 80)
        print(f" TEST {test_id}: {name}")
        print(f" STATO INIZIALE: {initial}")
        print(f" STATO ATTESO:   {expected}")
        print("-" * 80)
        print(" PASSAGGI ESEGUITI:")
        for i, step in enumerate(self.steps, 1):
            print(f"  {i}. {step}")
        
        wealth = self.get_current_wealth()
        print("\n [MEMORIA LOCALE NODI]")
        for n in self.relevant_nodes:
            for cid, state in n.channels.items():
                if state.commitments:
                    latest = state.commitments[-1]
                    readable_bals = {self.name_map.get(pk, pk[:8]): amt for pk, amt in latest.balances.items()}
                    pending = sum(h.amount for h in latest.htlcs if not h.resolved)
                    print(f"  {n.id:<6} | Canale {cid} | Bilancio: {readable_bals} | HTLC: {pending}")
        print(f"  >>> SALDO ATTUALE: {wealth}")

        print("\n [STATO BLOCKCHAIN]")
        for addr, ms in self.bc.addresses.items():
            final_view = self.get_final_chain_balances(addr)
            if ms.pending_close:
                pc = ms.pending_close
                broadcaster = self.name_map.get(pc.broadcaster, "Sconosciuto")
                print(f"  CONTRATTO {addr[:4]}... | CHIUSURA PENDENTE da {broadcaster}")
                print(f"  Risultato calcolato su Chain: {final_view}")
            elif ms.settlement:
                print(f"  CONTRATTO {addr[:4]}... | CHIUSO | Risultato Finale: {final_view}")
            else:
                print(f"  CONTRATTO {addr[:4]}... | APERTO | Fondi MultiSig: {ms.balance}")
        print("=" * 80 + "\n")
        self.steps = []
        self.claims_success = []
        self.claims_timeout = []

class TestSection1_Direct(LightningTestBase):
    def setUp(self):
        super().setUp()
        self.relevant_nodes = [self.alice, self.bob]
        self.ms = self.bc.create_multi_sig_address({self.alice.pub_key: 10, self.bob.pub_key: 10}, 2)
        self.cid = 101
        self.alice.init_channel(self.cid, self.ms.address, self.bob.pub_key, 20)
        self.bob.init_channel(self.cid, self.ms.address, self.alice.pub_key, 20)

    def test_d1_segreto_corretto(self):
        p_hash = self.bob.create_payment_hash()
        self.alice.sync_state_with(self.bob, self.cid, {self.alice.pub_key: 9, self.bob.pub_key: 10}, [HTLC(1, 1, p_hash, 100, self.alice.pub_key, self.bob.pub_key)])
        self.add_step("Alice crea HTLC da 1 verso Bob. Bob riscatta on-chain")
        tx = self.bob.channels[self.cid].commitments[0]
        self.bc.publish_commitment(self.ms.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": self.cid, "transaction_id": 0}, self.bob.pub_key, tx.revocation_hashes)
        self.bc.claim_htlc_success(self.ms.address, 1, self.bob.payment_secrets[p_hash])
        self.claims_success.append(1)
        
        # ASSERT: Bob deve avere 11 e Alice 9
        res = self.get_final_chain_balances(self.ms.address)
        self.assertEqual(res['Alice'], 9)
        self.assertEqual(res['Bob'], 11)
        self.print_snapshot("D1", "SEGRETO CORRETTO", "Alice=9, Bob=11", "10/10")

    def test_d2_time_hash_lock(self):
        self.add_step("Alice blocca 2 monete")
        self.alice.sync_state_with(self.bob, self.cid, {self.alice.pub_key: 8, self.bob.pub_key: 10}, [HTLC(2, 2, "h", 20, self.alice.pub_key, self.bob.pub_key)])
        # ASSERT: In memoria Alice deve avere 8
        self.assertEqual(self.alice.channels[self.cid].commitments[-1].balances[self.alice.pub_key], 8)
        self.print_snapshot("D2", "LOCK", "Alice=8 (2 bloccati)", "10/10")

    def test_d3_ritardo(self):
        self.add_step("Alice paga 3, Bob offline. Alice recupera")
        self.alice.sync_state_with(self.bob, self.cid, {self.alice.pub_key: 7, self.bob.pub_key: 10}, [HTLC(3, 3, "h", 10, self.alice.pub_key, self.bob.pub_key)])
        tx = self.alice.channels[self.cid].commitments[0]
        self.bc.publish_commitment(self.ms.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": self.cid, "transaction_id": 0}, self.alice.pub_key, tx.revocation_hashes)
        self.bc.mine(11)
        self.bc.claim_htlc_timeout(self.ms.address, 3)
        # ASSERT: Alice deve tornare a 10
        res = self.get_final_chain_balances(self.ms.address)
        self.assertEqual(res['Alice'], 10)
        self.print_snapshot("D3", "RITARDO", "Alice=10", "10/10")

    def test_d4_non_paga(self):
        self.add_step("Bob non collabora. Alice recupera 4 monete")
        self.alice.sync_state_with(self.bob, self.cid, {self.alice.pub_key: 6, self.bob.pub_key: 10}, [HTLC(4, 4, "h", 10, self.alice.pub_key, self.bob.pub_key)])
        tx = self.alice.channels[self.cid].commitments[0]
        self.bc.publish_commitment(self.ms.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": self.cid, "transaction_id": 0}, self.alice.pub_key, tx.revocation_hashes)
        self.bc.mine(11)
        self.bc.claim_htlc_timeout(self.ms.address, 4)
        self.assertEqual(self.get_final_chain_balances(self.ms.address)['Alice'], 10)
        self.print_snapshot("D4", "NON PAGA", "Alice=10", "10/10")

    def test_d5_ash_sbagliato(self):
        self.add_step("Bob usa segreto errato. Alice riprende 5 monete")
        self.alice.sync_state_with(self.bob, self.cid, {self.alice.pub_key: 5, self.bob.pub_key: 10}, [HTLC(5, 5, "h_v", 10, self.alice.pub_key, self.bob.pub_key)])
        tx = self.bob.channels[self.cid].commitments[0]
        self.bc.publish_commitment(self.ms.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": self.cid, "transaction_id": 0}, self.bob.pub_key, tx.revocation_hashes)
        with self.assertRaises(ValueError):
            self.bc.claim_htlc_success(self.ms.address, 5, "fake")
        self.bc.mine(11)
        self.bc.claim_htlc_timeout(self.ms.address, 5)
        self.assertEqual(self.get_final_chain_balances(self.ms.address)['Alice'], 10)
        self.print_snapshot("D5", "ASH ERRATO", "Alice=10", "10/10")

    def test_d6_timeout_lungo(self):
        self.add_step("Timeout 100 blocchi")
        self.alice.sync_state_with(self.bob, self.cid, {self.alice.pub_key: 4, self.bob.pub_key: 10}, [HTLC(6, 6, "h", 100, self.alice.pub_key, self.bob.pub_key)])
        tx = self.alice.channels[self.cid].commitments[0]
        self.bc.publish_commitment(self.ms.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": self.cid, "transaction_id": 0}, self.alice.pub_key, tx.revocation_hashes)
        self.bc.mine(101)
        self.bc.claim_htlc_timeout(self.ms.address, 6)
        self.assertEqual(self.get_final_chain_balances(self.ms.address)['Alice'], 10)
        self.print_snapshot("D6", "TIMEOUT LUNGO", "Alice=10", "10/10")

    def test_d7_timeout_breve(self):
        self.add_step("Tenta rimborso al blocco 1 (scade al 10)")
        self.alice.sync_state_with(self.bob, self.cid, {self.alice.pub_key: 3, self.bob.pub_key: 10}, [HTLC(7, 7, "h", 10, self.alice.pub_key, self.bob.pub_key)])
        tx = self.alice.channels[self.cid].commitments[0]
        self.bc.publish_commitment(self.ms.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": self.cid, "transaction_id": 0}, self.alice.pub_key, tx.revocation_hashes)
        self.bc.mine(1)
        with self.assertRaises(ValueError):
            self.bc.claim_htlc_timeout(self.ms.address, 7)
        self.print_snapshot("D7", "TIMEOUT BREVE", "Blocco rimborso", "10/10")

class TestSection2_Chain(LightningTestBase):
    def setUp(self):
        super().setUp()
        self.relevant_nodes = self.all_nodes
        self.ms_ac = self.bc.create_multi_sig_address({self.alice.pub_key: 10, self.carol.pub_key: 10}, 2)
        self.ms_cd = self.bc.create_multi_sig_address({self.carol.pub_key: 10, self.dave.pub_key: 10}, 2)
        self.ms_db = self.bc.create_multi_sig_address({self.dave.pub_key: 10, self.bob.pub_key: 10}, 2)
        self.alice.init_channel(1, self.ms_ac.address, self.carol.pub_key, 20)
        self.carol.init_channel(1, self.ms_ac.address, self.alice.pub_key, 20)
        self.carol.init_channel(2, self.ms_cd.address, self.dave.pub_key, 20)
        self.dave.init_channel(2, self.ms_cd.address, self.carol.pub_key, 20)
        self.dave.init_channel(3, self.ms_db.address, self.bob.pub_key, 20)
        self.bob.init_channel(3, self.ms_db.address, self.dave.pub_key, 20)

    def test_c1_catena_successo(self):
        p_hash = self.bob.create_payment_hash()
        self.alice.sync_state_with(self.carol, 1, {self.alice.pub_key: 6, self.carol.pub_key: 10}, [HTLC(1, 4, p_hash, 40, self.alice.pub_key, self.carol.pub_key)])
        self.carol.sync_state_with(self.dave, 2, {self.carol.pub_key: 6, self.dave.pub_key: 10}, [HTLC(2, 4, p_hash, 30, self.carol.pub_key, self.dave.pub_key)])
        self.dave.sync_state_with(self.bob, 3, {self.dave.pub_key: 6, self.bob.pub_key: 10}, [HTLC(3, 4, p_hash, 20, self.dave.pub_key, self.bob.pub_key)])
        
        self.add_step("Bob rivela segreto. Alice paga 4 a Bob via catena")
        self.dave.sync_state_with(self.bob, 3, {self.dave.pub_key: 6, self.bob.pub_key: 14}, [])
        self.carol.sync_state_with(self.dave, 2, {self.carol.pub_key: 6, self.dave.pub_key: 14}, [])
        self.alice.sync_state_with(self.carol, 1, {self.alice.pub_key: 6, self.carol.pub_key: 14}, [])
        
        # ASSERT: Alice ha 6, Bob 14, Carol e Dave hanno 20 totali
        w = self.get_current_wealth()
        self.assertEqual(w['Alice'], 6)
        self.assertEqual(w['Bob'], 14)
        self.assertEqual(w['Carol'], 20)
        self.assertEqual(w['Dave'], 20)
        self.print_snapshot("C1", "CATENA", "A:6, B:14, Interm:20", "Wealth: A:10, B:10, C:20, D:20")

    def test_c3_catena_ritardo(self):
        self.add_step("Dave paga 5 a Bob. Bob offline. Dave recupera")
        self.dave.sync_state_with(self.bob, 3, {self.dave.pub_key: 5, self.bob.pub_key: 10}, [HTLC(300, 5, "h", 10, self.dave.pub_key, self.bob.pub_key)])
        tx = self.dave.channels[3].commitments[0]
        self.bc.publish_commitment(self.ms_db.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": 3, "transaction_id": 0}, self.dave.pub_key, tx.revocation_hashes)
        self.bc.mine(11)
        self.bc.claim_htlc_timeout(self.ms_db.address, 300)
        self.assertEqual(self.get_final_chain_balances(self.ms_db.address)['Dave'], 10)
        self.print_snapshot("C3", "CATENA RITARDO", "Dave torna a 10", "D=10, B=10")

    def test_c4_catena_nopay(self):
        self.add_step("Carol rimborsata da Dave dopo timeout di 6 monete")
        self.carol.sync_state_with(self.dave, 2, {self.carol.pub_key: 4, self.dave.pub_key: 10}, [HTLC(400, 6, "h", 10, self.carol.pub_key, self.dave.pub_key)])
        tx = self.carol.channels[2].commitments[0]
        self.bc.publish_commitment(self.ms_cd.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": 2, "transaction_id": 0}, self.carol.pub_key, tx.revocation_hashes)
        self.bc.mine(11)
        self.bc.claim_htlc_timeout(self.ms_cd.address, 400)
        self.assertEqual(self.get_final_chain_balances(self.ms_cd.address)['Carol'], 10)
        self.print_snapshot("C4", "CATENA NON PAGA", "Carol torna a 10", "C=10, D=10")

    def test_c5_chain_ash_errato(self):
        self.add_step("Dave recupera 7 monete dopo segreto errato di Bob")
        self.dave.sync_state_with(self.bob, 3, {self.dave.pub_key: 3, self.bob.pub_key: 10}, [HTLC(500, 7, "h_v", 10, self.dave.pub_key, self.bob.pub_key)])
        tx = self.bob.channels[3].commitments[0]
        self.bc.publish_commitment(self.ms_db.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": 3, "transaction_id": 0}, self.bob.pub_key, tx.revocation_hashes)
        with self.assertRaises(ValueError):
            self.bc.claim_htlc_success(self.ms_db.address, 500, "fake")
        self.bc.mine(11)
        self.bc.claim_htlc_timeout(self.ms_db.address, 500)
        self.assertEqual(self.get_final_chain_balances(self.ms_db.address)['Dave'], 10)
        self.print_snapshot("C5", "ASH ERRATO CATENA", "Dave torna a 10", "D=10, B=10")

    def test_c2_chain_lock(self):
        self.add_step("Inoltro catena 8 monete. Fondi in volo")
        self.alice.sync_state_with(self.carol, 1, {self.alice.pub_key: 2, self.carol.pub_key: 10}, [HTLC(20, 8, "h", 40, self.alice.pub_key, self.carol.pub_key)])
        self.assertEqual(self.alice.channels[1].commitments[-1].balances[self.alice.pub_key], 2)
        self.print_snapshot("C2", "LOCK CATENA", "A ha 2, 8 in HTLC", "10/10")

    def test_c6_chain_long(self):
        self.add_step("Timeout catena blocco 100")
        self.alice.sync_state_with(self.carol, 1, {self.alice.pub_key: 1, self.carol.pub_key: 10}, [HTLC(60, 9, "h", 100, self.alice.pub_key, self.carol.pub_key)])
        tx = self.alice.channels[1].commitments[0]
        self.bc.publish_commitment(self.ms_ac.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": 1, "transaction_id": 0}, self.alice.pub_key, tx.revocation_hashes)
        self.bc.mine(101)
        self.bc.claim_htlc_timeout(self.ms_ac.address, 60)
        self.assertEqual(self.get_final_chain_balances(self.ms_ac.address)['Alice'], 10)
        self.print_snapshot("C6", "LONG TIMEOUT CATENA", "Alice recupera 9", "10/10")

    def test_c7_chain_short(self):
        self.add_step("Tenta rimborso Carol blocco 1")
        self.carol.sync_state_with(self.dave, 2, {self.carol.pub_key: 5, self.dave.pub_key: 10}, [HTLC(70, 5, "h", 10, self.carol.pub_key, self.dave.pub_key)])
        tx = self.carol.channels[2].commitments[0]
        self.bc.publish_commitment(self.ms_cd.address, tx.balances, tx.htlcs, tx.signatures, {"channel_id": 2, "transaction_id": 0}, self.carol.pub_key, tx.revocation_hashes)
        self.bc.mine(1)
        with self.assertRaises(ValueError):
            self.bc.claim_htlc_timeout(self.ms_cd.address, 70)
        self.print_snapshot("C7", "SHORT TIMEOUT CATENA", "Blocco Blockchain", "10/10")

if __name__ == "__main__":
    unittest.main()