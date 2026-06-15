from dataclasses import dataclass, field

from blockchain import BlockChain


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


class LightningNetwork:
    def __init__(self, blockchain: BlockChain):
        self.blockchain = blockchain
        self.channels: dict[int, Channel] = {}
        self.next_channel_id = 0

    def open_channel(self, contributions: dict[str, int]) -> Channel:
        if len(contributions) != 2:
            raise ValueError("un canale Lightning base ha esattamente due partecipanti")
        if any(amount <= 0 for amount in contributions.values()):
            raise ValueError("ogni contributo deve essere positivo")

        participants = tuple(sorted(contributions))
        capacity = sum(contributions.values())
        funding_wallet = self.blockchain.create_multi_sig_address(list(participants), 2)
        self.blockchain.deposit(funding_wallet.address, capacity)

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
        funding_wallet = self.blockchain.get_address(channel.funding_address)
        transaction = self.get_commitment_transaction(channel, transaction_id)

        if not self.blockchain.has_enough_valid_signatures(funding_wallet, signatures):
            raise ValueError("servono entrambe le firme per chiudere il canale")
        if not self.blockchain.has_enough_valid_signatures(
            funding_wallet, list(transaction.signatures)
        ):
            raise ValueError("la commitment transaction non e' firmata correttamente")

        if sum(transaction.balances.values()) != channel.capacity:
            raise ValueError("stato del canale incoerente")

        funding_wallet.balance = 0
        channel.is_open = False
        return dict(transaction.balances)

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
