from actors import Actors
from blockchain import BlockChain
from lightning_network import LightningNetwork


def main():
    bc = BlockChain()
    ln = LightningNetwork(bc)
    ac = Actors()

    alice = ac.create_actor("alice", "Alice")
    bob = ac.create_actor("bob", "Bob")

    funding_wallet = bc.create_multi_sig_address(
        {alice.public_key: 10, bob.public_key: 5},
        2,
    )

    channel = ln.open_channel(funding_wallet.address)
    print(channel)

    def collect_revocation_hashes(transaction_id, actors):
        return {
            actor.public_key: actor.create_revocation_hash(
                channel.channel_id,
                transaction_id,
            )
            for actor in actors
        }

    # ========tx0============
    tx0_id = ln.next_transaction_id(channel.channel_id)
    tx0_hashes = collect_revocation_hashes(tx0_id, (alice, bob))

    # creazione transazione tx0
    tx0 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 10,
            bob.public_key: 5,
        },
        tx0_hashes,
    )

    # i due attori firmano la transazione tx0
    tx0.add_signature(alice.public_key, alice.sign(tx0.payload()))
    tx0.add_signature(bob.public_key, bob.sign(tx0.payload()))

    # ========tx1============
    tx1_id = ln.next_transaction_id(channel.channel_id)
    tx1_hashes = collect_revocation_hashes(tx1_id, (alice, bob))

    # creazione transazione tx1
    tx1 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 8,
            bob.public_key: 7,
        },
        tx1_hashes,
    )

    # i due attori firmano la transazione tx1
    tx1.add_signature(alice.public_key, alice.sign(tx1.payload()))
    tx1.add_signature(bob.public_key, bob.sign(tx1.payload()))

    # i due attori si rivelano i segreti della transazione precedente (tx0)
    ln.reveal_revocation_secret(
        channel.channel_id,
        tx0.transaction_id,
        alice.public_key,
        alice.get_revocation_secret(tx0.transaction_id),
    )
    ln.reveal_revocation_secret(
        channel.channel_id,
        tx0.transaction_id,
        bob.public_key,
        bob.get_revocation_secret(tx0.transaction_id),
    )

    # ========tx2============
    tx2_id = ln.next_transaction_id(channel.channel_id)
    tx2_hashes = collect_revocation_hashes(tx2_id, (alice, bob))
    tx2 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 9,
            bob.public_key: 6,
        },
        tx2_hashes,
    )

    # i due attori firmano la transazione tx2
    tx2.add_signature(alice.public_key, alice.sign(tx2.payload()))
    tx2.add_signature(bob.public_key, bob.sign(tx2.payload()))

    # i due attori si rivelano i segreti della transazione precedente (tx1)
    ln.reveal_revocation_secret(
        channel.channel_id,
        tx1.transaction_id,
        alice.public_key,
        alice.get_revocation_secret(tx1.transaction_id),
    )
    ln.reveal_revocation_secret(
        channel.channel_id,
        tx1.transaction_id,
        bob.public_key,
        bob.get_revocation_secret(tx1.transaction_id),
    )

    # Bob prova a chiudere on-chain con tx1, che e' vecchia rispetto a tx2.
    ln.publish_commitment(
        channel.channel_id,
        tx1.transaction_id,
        broadcaster=bob.public_key,
        challenge_period=2,
    )
    bob_tx1_secret = ln.get_revealed_revocation_secret(
        channel.channel_id,
        tx1.transaction_id,
        bob.public_key,
    )
    final_balances = bc.punish_commitment(
        funding_wallet.address,
        punished_party=bob.public_key,
        beneficiary=alice.public_key,
        secret=bob_tx1_secret,
    )
    print(f"punishment balances: {final_balances}")


if __name__ == "__main__":
    main()
