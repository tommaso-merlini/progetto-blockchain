from actors import Actors
from blockchain import BlockChain
from lightning_network import LightningNetwork


def main():
    bc = BlockChain()
    ln = LightningNetwork(bc)
    ac = Actors()

    alice = ac.create_actor("alice", "Alice")
    bob = ac.create_actor("bob", "Bob")

    channel = ln.open_channel({alice.public_key: 10, bob.public_key: 5})
    print(channel)

    tx0 = ln.pay_in_channel(channel.channel_id, alice.public_key, bob.public_key, 2)
    tx0.add_signature(alice.public_key, alice.sign(tx0.payload()))
    tx0.add_signature(bob.public_key, bob.sign(tx0.payload()))

    tx1 = ln.pay_in_channel(channel.channel_id, bob.public_key, alice.public_key, 1)
    tx1.add_signature(alice.public_key, alice.sign(tx1.payload()))
    tx1.add_signature(bob.public_key, bob.sign(tx1.payload()))

    tx2 = ln.pay_in_channel(channel.channel_id, alice.public_key, bob.public_key, 4)
    tx2.add_signature(alice.public_key, alice.sign(tx2.payload()))
    tx2.add_signature(bob.public_key, bob.sign(tx2.payload()))

    print(f"current balances: {channel.balances}")
    print(f"tx{tx0.transaction_id} unlocks: {tx0.balances}")
    print(f"tx{tx1.transaction_id} unlocks: {tx1.balances}")
    print(f"tx{tx2.transaction_id} unlocks: {tx2.balances}")

    # TODO: invalidare le transazioni passate
    final_balances = ln.close_channel(
        channel.channel_id,
        tx2.transaction_id,
    )
    print(final_balances)


if __name__ == "__main__":
    main()
