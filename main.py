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

    tx0 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 10,
            bob.public_key: 5,
        },
    )
    tx0.add_signature(alice.public_key, alice.sign(tx0.payload()))
    tx0.add_signature(bob.public_key, bob.sign(tx0.payload()))

    tx1 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 8,
            bob.public_key: 7,
        },
    )
    tx1.add_signature(alice.public_key, alice.sign(tx1.payload()))
    tx1.add_signature(bob.public_key, bob.sign(tx1.payload()))

    tx2 = ln.create_transaction(
        channel.channel_id,
        {
            alice.public_key: 9,
            bob.public_key: 6,
        },
    )
    tx2.add_signature(alice.public_key, alice.sign(tx2.payload()))
    tx2.add_signature(bob.public_key, bob.sign(tx2.payload()))

    # TODO: invalidare le transazioni passate
    final_balances = ln.close_channel(
        channel.channel_id,
        tx2.transaction_id,
    )
    print(f"final balances: {final_balances}")


if __name__ == "__main__":
    main()
