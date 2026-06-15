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
    tx1 = ln.pay_in_channel(channel.channel_id, bob.public_key, alice.public_key, 1)
    tx2 = ln.pay_in_channel(channel.channel_id, alice.public_key, bob.public_key, 4)

    print(f"current balances: {channel.balances}")
    print(f"tx{tx0.transaction_id} unlocks: {tx0.balances}")
    print(f"tx{tx1.transaction_id} unlocks: {tx1.balances}")
    print(f"tx{tx2.transaction_id} unlocks: {tx2.balances}")

    final_balances = ln.close_channel(
        channel.channel_id,
        tx2.transaction_id,
        [alice.public_key, bob.public_key],
    )
    print(final_balances)

    # TODO: applicare questa transazione nella blockchain


if __name__ == "__main__":
    main()
