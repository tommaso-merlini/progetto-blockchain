from blockchain import BlockChain
from lightning_network import LightningNetwork


def main():
    bc = BlockChain()
    ln = LightningNetwork(bc)

    channel = ln.open_channel({"alice": 10, "bob": 5})
    print(channel)

    tx0 = ln.pay_in_channel(channel.channel_id, "alice", "bob", 2)
    tx1 = ln.pay_in_channel(channel.channel_id, "bob", "alice", 1)
    tx2 = ln.pay_in_channel(channel.channel_id, "alice", "bob", 4)

    print(f"current balances: {channel.balances}")
    print(f"tx{tx0.transaction_id} unlocks: {tx0.balances}")
    print(f"tx{tx1.transaction_id} unlocks: {tx1.balances}")
    print(f"tx{tx2.transaction_id} unlocks: {tx2.balances}")

    final_balances = ln.close_channel(
        channel.channel_id, tx2.transaction_id, ["alice", "bob"]
    )
    print(final_balances)

    # TODO: applicare questa transazione nella blockchain


if __name__ == "__main__":
    main()
