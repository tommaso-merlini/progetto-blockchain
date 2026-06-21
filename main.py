from blockchain import BlockChain
from actors import Actor
from domain_types import HTLC

def run_multi_hop_demo():
    print("\n=== LIGHTNING NETWORK: MULTI-HOP DEMO (Alice -> Carol -> Dave -> Bob) ===")
    bc = BlockChain(verbose=True)
    
    # Inizializzazione Nodi
    alice = Actor("Alice", verbose=True)
    carol = Actor("Carol", verbose=True)
    dave = Actor("Dave", verbose=True)
    bob = Actor("Bob", verbose=True)

    # 1. Apertura Canali (Il Grafo)
    # Alice <-> Carol
    ms_ac = bc.create_multi_sig_address({alice.pub_key: 10, carol.pub_key: 10}, 2)
    cid_ac = 1
    alice.init_channel(cid_ac, ms_ac.address, carol.pub_key, 20)
    carol.init_channel(cid_ac, ms_ac.address, alice.pub_key, 20)

    # Carol <-> Dave
    ms_cd = bc.create_multi_sig_address({carol.pub_key: 10, dave.pub_key: 10}, 2)
    cid_cd = 2
    carol.init_channel(cid_cd, ms_cd.address, dave.pub_key, 20)
    dave.init_channel(cid_cd, ms_cd.address, carol.pub_key, 20)

    # Dave <-> Bob
    ms_db = bc.create_multi_sig_address({dave.pub_key: 10, bob.pub_key: 10}, 2)
    cid_db = 3
    dave.init_channel(cid_db, ms_db.address, bob.pub_key, 20)
    bob.init_channel(cid_db, ms_db.address, dave.pub_key, 20)

    # 2. Bob genera una fattura (Payment Hash)
    p_hash = bob.create_payment_hash()
    print(f"\n[INFO] Bob ha generato il Payment Hash: {p_hash[:10]}...")

    # 3. Costruzione della catena di HTLC (Forwarding)
    print("\n--- STEP 1: Alice blocca i fondi verso Carol ---")
    h1 = HTLC(1, 5, p_hash, 40, alice.pub_key, carol.pub_key)
    alice.sync_state_with(carol, cid_ac, {alice.pub_key: 5, carol.pub_key: 10}, [h1])

    print("\n--- STEP 2: Carol blocca i fondi verso Dave ---")
    h2 = HTLC(2, 5, p_hash, 30, carol.pub_key, dave.pub_key)
    carol.sync_state_with(dave, cid_cd, {carol.pub_key: 5, dave.pub_key: 10}, [h2])

    print("\n--- STEP 3: Dave blocca i fondi verso Bob ---")
    h3 = HTLC(3, 5, p_hash, 20, dave.pub_key, bob.pub_key)
    dave.sync_state_with(bob, cid_db, {dave.pub_key: 5, bob.pub_key: 10}, [h3])

    # 4. Risoluzione della catena (Bob rivela il segreto a ritroso)
    secret = bob.payment_secrets[p_hash]
    print(f"\n--- STEP 4: Bob rivela il segreto {secret[:8]}... a Dave ---")
    # Dave scopre il segreto, aggiornano il canale DB: rimuovono HTLC e aggiornano bilanci
    dave.known_secrets[p_hash] = secret
    dave.sync_state_with(bob, cid_db, {dave.pub_key: 5, bob.pub_key: 15}, [])

    print("\n--- STEP 5: Dave rivela il segreto a Carol ---")
    carol.known_secrets[p_hash] = secret
    carol.sync_state_with(dave, cid_cd, {carol.pub_key: 5, dave.pub_key: 15}, [])

    print("\n--- STEP 6: Carol rivela il segreto ad Alice ---")
    alice.known_secrets[p_hash] = secret
    alice.sync_state_with(carol, cid_ac, {alice.pub_key: 5, carol.pub_key: 15}, [])

    print("\n=== PAGAMENTO COMPLETATO! ===")
    print(f"Alice (Mittente) bilancio finale: {alice.channels[cid_ac].commitments[-1].balances[alice.pub_key]}")
    print(f"Bob (Destinatario) bilancio finale: {bob.channels[cid_db].commitments[-1].balances[bob.pub_key]}")

if __name__ == "__main__":
    run_multi_hop_demo()