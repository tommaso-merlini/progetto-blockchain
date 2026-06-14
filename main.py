from dataclasses import dataclass, field
import hashlib
import json


@dataclass
class MultiSigAddress:
    address: str
    public_keys: tuple[str, ...]
    threshold: int
    balance: int = 0


@dataclass
class CommitmentTransaction:
    transaction_id: int
    channel_id: int
    funding_address: str
    balances: dict[str, int]
    signatures: tuple[str, ...]


@dataclass
class Channel:
    channel_id: int
    funding_address: str
    participants: tuple[str, ...]
    capacity: int
    balances: dict[str, int]
    commitment_transactions: dict[int, CommitmentTransaction] = field(
        default_factory=dict
    )
    next_transaction_id: int = 0
    is_open: bool = True


class BlockChain:
    def __init__(self):
        self.addresses: dict[str, MultiSigAddress] = {}
        self.channels: dict[int, Channel] = {}
        self.next_channel_id = 0

    def create_multi_sig_address(
        self, public_keys: list[str], threshold: int
    ) -> MultiSigAddress:
        unique_public_keys = tuple(sorted(set(public_keys)))

        if not unique_public_keys:
            raise ValueError("servono almeno una public key")
        if threshold < 1:
            raise ValueError("la threshold deve essere almeno 1")
        if threshold > len(unique_public_keys):
            raise ValueError("la threshold non puo' superare il numero di public key")

        address = self.derive_address(unique_public_keys, threshold)
        multi_sig_address = MultiSigAddress(address, unique_public_keys, threshold)
        self.addresses[address] = multi_sig_address
        return multi_sig_address

    def deposit(self, address: str, amount: int):
        if amount <= 0:
            raise ValueError("l'importo deve essere positivo")

        multi_sig_address = self.get_address(address)
        multi_sig_address.balance += amount

    def spend(
        self,
        from_address: str,
        to_address: str,
        amount: int,
        signatures: list[str],
    ):
        if amount <= 0:
            raise ValueError("l'importo deve essere positivo")

        multi_sig_address = self.get_address(from_address)
        if amount > multi_sig_address.balance:
            raise ValueError("saldo insufficiente")
        if not self.has_enough_valid_signatures(multi_sig_address, signatures):
            raise ValueError("firme valide insufficienti")

        multi_sig_address.balance -= amount
        print(f"sent {amount} from {from_address} to {to_address}")

    def open_lightning_channel(self, contributions: dict[str, int]) -> Channel:
        if len(contributions) != 2:
            raise ValueError("un canale Lightning base ha esattamente due partecipanti")
        if any(amount <= 0 for amount in contributions.values()):
            raise ValueError("ogni contributo deve essere positivo")

        participants = tuple(sorted(contributions))
        capacity = sum(contributions.values())
        funding_wallet = self.create_multi_sig_address(list(participants), 2)
        self.deposit(funding_wallet.address, capacity)

        channel = Channel(
            channel_id=self.next_channel_id,
            funding_address=funding_wallet.address,
            participants=participants,
            capacity=capacity,
            balances={
                participant: contributions[participant] for participant in participants
            },
        )
        self.channels[channel.channel_id] = channel
        self.next_channel_id += 1
        return channel

    def pay_in_channel(
        self, channel_id: int, sender: str, recipient: str, amount: int
    ) -> CommitmentTransaction:
        channel = self.get_open_channel(channel_id)

        if sender not in channel.balances or recipient not in channel.balances:
            raise ValueError("sender e recipient devono essere nel canale")
        if amount <= 0:
            raise ValueError("l'importo deve essere positivo")
        if channel.balances[sender] < amount:
            raise ValueError("saldo del sender insufficiente nel canale")

        channel.balances[sender] -= amount
        channel.balances[recipient] += amount
        return self.create_commitment_transaction(channel)

    def create_commitment_transaction(self, channel: Channel) -> CommitmentTransaction:
        transaction = CommitmentTransaction(
            transaction_id=channel.next_transaction_id,
            channel_id=channel.channel_id,
            funding_address=channel.funding_address,
            balances=dict(channel.balances),
            signatures=channel.participants,
        )
        channel.commitment_transactions[transaction.transaction_id] = transaction
        channel.next_transaction_id += 1
        return transaction

    def close_channel(
        self, channel_id: int, transaction_id: int, signatures: list[str]
    ) -> dict[str, int]:
        channel = self.get_open_channel(channel_id)
        funding_wallet = self.get_address(channel.funding_address)
        transaction = self.get_commitment_transaction(channel, transaction_id)

        if not self.has_enough_valid_signatures(funding_wallet, signatures):
            raise ValueError("servono entrambe le firme per chiudere il canale")
        if not self.has_enough_valid_signatures(
            funding_wallet, list(transaction.signatures)
        ):
            raise ValueError("la commitment transaction non e' firmata correttamente")

        if sum(transaction.balances.values()) != channel.capacity:
            raise ValueError("stato del canale incoerente")

        funding_wallet.balance = 0
        channel.is_open = False
        return dict(transaction.balances)

    def derive_address(self, public_keys: tuple[str, ...], threshold: int) -> str:
        payload = json.dumps(
            {"public_keys": public_keys, "threshold": threshold},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:40]

    def get_address(self, address: str) -> MultiSigAddress:
        if address not in self.addresses:
            raise ValueError("address sconosciuto")
        return self.addresses[address]

    def has_enough_valid_signatures(
        self, multi_sig_address: MultiSigAddress, signatures: list[str]
    ) -> bool:
        valid_signers = set(signatures).intersection(multi_sig_address.public_keys)
        return len(valid_signers) >= multi_sig_address.threshold

    def get_open_channel(self, channel_id: int) -> Channel:
        if channel_id not in self.channels:
            raise ValueError("canale sconosciuto")

        channel = self.channels[channel_id]
        if not channel.is_open:
            raise ValueError("canale gia' chiuso")
        return channel

    def get_commitment_transaction(
        self, channel: Channel, transaction_id: int
    ) -> CommitmentTransaction:
        if transaction_id not in channel.commitment_transactions:
            raise ValueError("commitment transaction sconosciuta")
        return channel.commitment_transactions[transaction_id]

    def __str__(self):
        return str(self.addresses)


def main():
    bc = BlockChain()

    channel = bc.open_lightning_channel({"alice": 10, "bob": 5})
    print(channel)

    tx0 = bc.pay_in_channel(channel.channel_id, "alice", "bob", 2)
    tx1 = bc.pay_in_channel(channel.channel_id, "bob", "alice", 1)
    tx2 = bc.pay_in_channel(channel.channel_id, "alice", "bob", 4)

    print(f"current balances: {channel.balances}")
    print(f"tx{tx0.transaction_id} unlocks: {tx0.balances}")
    print(f"tx{tx1.transaction_id} unlocks: {tx1.balances}")
    print(f"tx{tx2.transaction_id} unlocks: {tx2.balances}")

    final_balances = bc.close_channel(
        channel.channel_id, tx2.transaction_id, ["alice", "bob"]
    )
    print(final_balances)


if __name__ == "__main__":
    main()
