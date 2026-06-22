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
    alice.open_local_channel(channel, bob.public_key)
    bob.open_local_channel(channel, alice.public_key)
    print(channel)

    def collect_revocation_hashes(transaction_id):
        return {
            actor.public_key: actor.create_channel_revocation_hash(
                channel.channel_id,
                transaction_id,
            )
            for actor in (alice, bob)
        }

    def update_channel(proposer, receiver, balances):
        transaction_id = proposer.get_local_channel(
            channel.channel_id
        ).next_transaction_id
        transaction = proposer.propose_commitment(
            ln,
            channel.channel_id,
            balances,
            collect_revocation_hashes(transaction_id),
        )
        receiver.receive_commitment_proposal(ln, transaction, proposer.public_key)
        proposer.receive_signed_commitment(ln, transaction, receiver.public_key)
        return transaction

    tx0 = update_channel(
        alice,
        bob,
        {
            alice.public_key: 10,
            bob.public_key: 5,
        },
    )

    tx1 = update_channel(
        alice,
        bob,
        {
            alice.public_key: 8,
            bob.public_key: 7,
        },
    )

    alice_tx0_secret = alice.reveal_previous_secret(
        channel.channel_id,
        tx0.transaction_id,
    )
    bob.receive_revocation_secret(tx0, alice.public_key, alice_tx0_secret)
    bob_tx0_secret = bob.reveal_previous_secret(channel.channel_id, tx0.transaction_id)
    alice.receive_revocation_secret(tx0, bob.public_key, bob_tx0_secret)

    tx2 = update_channel(
        alice,
        bob,
        {
            alice.public_key: 9,
            bob.public_key: 6,
        },
    )

    alice_tx1_secret = alice.reveal_previous_secret(
        channel.channel_id,
        tx1.transaction_id,
    )
    bob.receive_revocation_secret(tx1, alice.public_key, alice_tx1_secret)
    bob_tx1_secret = bob.reveal_previous_secret(channel.channel_id, tx1.transaction_id)
    alice.receive_revocation_secret(tx1, bob.public_key, bob_tx1_secret)

    # Bob prova a chiudere on-chain con tx1, che e' vecchia rispetto a tx2.
    ln.publish_commitment(
        tx1,
        broadcaster=bob.public_key,
        challenge_period=2,
    )
    bob_tx1_secret = alice.get_counterparty_revocation_secret(
        channel.channel_id,
        tx1.transaction_id,
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
