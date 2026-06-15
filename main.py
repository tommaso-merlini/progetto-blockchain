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

    def create_signed_commitment(balances):
        revocation_secrets = {
            alice.public_key: ln.generate_revocation_secret(),
            bob.public_key: ln.generate_revocation_secret(),
        }
        tx = ln.create_transaction(
            channel.channel_id,
            balances,
            revocation_secrets,
        )
        tx.add_signature(alice.public_key, alice.sign(tx.payload()))
        tx.add_signature(bob.public_key, bob.sign(tx.payload()))
        return tx, revocation_secrets

        # tx0, tx0_secrets = create_signed_commitment(
        #     {
        #         alice.public_key: 10,
        #         bob.public_key: 5,
        #     }
        # )

    # tx0
    tx0_secrets = {
        alice.public_key: ln.generate_revocation_secret(),
        bob.public_key: ln.generate_revocation_secret(),
    }
    tx0 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 10,
            bob.public_key: 5,
        },
        tx0_secrets,
    )
    tx0.add_signature(alice.public_key, alice.sign(tx0.payload()))
    tx0.add_signature(bob.public_key, bob.sign(tx0.payload()))

    # tx1
    tx1_secrets = {
        alice.public_key: ln.generate_revocation_secret(),
        bob.public_key: ln.generate_revocation_secret(),
    }
    tx1 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 8,
            bob.public_key: 7,
        },
        tx1_secrets,
    )
    tx1.add_signature(alice.public_key, alice.sign(tx1.payload()))
    tx1.add_signature(bob.public_key, bob.sign(tx1.payload()))
    ln.reveal_revocation_secret(
        channel.channel_id,
        tx1.transaction_id,
        alice.public_key,
        tx1_secrets[alice.public_key],
    )
    ln.reveal_revocation_secret(
        channel.channel_id,
        tx1.transaction_id,
        bob.public_key,
        tx1_secrets[bob.public_key],
    )

    # tx2
    tx2_secrets = {
        alice.public_key: ln.generate_revocation_secret(),
        bob.public_key: ln.generate_revocation_secret(),
    }
    tx2 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 9,
            bob.public_key: 6,
        },
        tx2_secrets,
    )
    tx2.add_signature(alice.public_key, alice.sign(tx2.payload()))
    tx2.add_signature(bob.public_key, bob.sign(tx2.payload()))
    ln.reveal_revocation_secret(
        channel.channel_id,
        tx2.transaction_id,
        alice.public_key,
        tx2_secrets[alice.public_key],
    )
    ln.reveal_revocation_secret(
        channel.channel_id,
        tx2.transaction_id,
        bob.public_key,
        tx2_secrets[bob.public_key],
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
