from dataclasses import dataclass, field

from blockchain import BlockChain
from domain_types import (
    Address,
    Balances,
    ChannelId,
    Money,
    PublicKey,
    Signature,
    TransactionId,
)


@dataclass
class CommitmentTransaction:
    transaction_id: TransactionId
    channel_id: ChannelId
    funding_address: Address
    balances: Balances
    signatures: dict[PublicKey, Signature] = field(default_factory=dict)

    def payload_metadata(self) -> dict[str, int]:
        return {
            "transaction_id": self.transaction_id,
            "channel_id": self.channel_id,
        }

    def payload(self) -> bytes:
        return BlockChain.multisig_spend_payload(
            self.funding_address,
            self.balances,
            self.payload_metadata(),
        )

    def add_signature(self, public_key: PublicKey, signature: Signature):
        self.signatures[public_key] = signature


@dataclass
class Channel:
    channel_id: ChannelId
    funding_address: Address
    participants: tuple[PublicKey, ...]
    capacity: Money
    commitments: list[CommitmentTransaction] = field(default_factory=list)
    is_open: bool = True


class LightningNetwork:
    def __init__(self, blockchain: BlockChain):
        self.blockchain = blockchain
        self.channels: dict[ChannelId, Channel] = {}
        self.next_channel_id: ChannelId = 0

    # inizializza il channel bidirezionale nella LN usando un MultiSigAddress esistente
    def open_channel(self, funding_address: Address) -> Channel:
        funding_wallet = self.blockchain.get_address(funding_address)

        if len(funding_wallet.initial_balances) != 2:
            raise ValueError("un canale Lightning base ha esattamente due partecipanti")
        if funding_wallet.threshold != 2:
            raise ValueError("un canale Lightning base usa un multisig 2-of-2")

        channel = Channel(
            channel_id=self.next_channel_id,
            funding_address=funding_address,
            participants=funding_wallet.public_keys,
            capacity=sum(funding_wallet.initial_balances.values()),
        )
        self.channels[channel.channel_id] = channel
        self.next_channel_id += 1
        return channel

    def create_transaction(
        self,
        channel_id: ChannelId,
        balances: Balances,
    ) -> CommitmentTransaction:
        channel = self.get_open_channel(channel_id)
        self.validate_commitment_balances(channel, balances)

        transaction = CommitmentTransaction(
            transaction_id=len(channel.commitments),
            channel_id=channel.channel_id,
            funding_address=channel.funding_address,
            balances=dict(balances),
        )
        channel.commitments.append(transaction)
        return transaction

    def create_commitment(
        self,
        channel_id: ChannelId,
        balances: Balances,
    ) -> CommitmentTransaction:
        return self.create_transaction(channel_id, balances)

    def close_channel(
        self,
        channel_id: ChannelId,
        transaction_id: TransactionId,
    ) -> Balances:
        channel = self.get_open_channel(channel_id)
        funding_wallet = self.blockchain.get_address(channel.funding_address)
        transaction = self.get_commitment_transaction(channel, transaction_id)

        if not self.blockchain.has_enough_valid_signatures(
            funding_wallet, transaction.payload(), transaction.signatures
        ):
            raise ValueError("la commitment transaction non e' firmata correttamente")

        self.validate_commitment_balances(channel, transaction.balances)

        self.blockchain.spend_multisig(
            funding_wallet.address,
            transaction.balances,
            transaction.signatures,
            transaction.payload_metadata(),
        )
        channel.is_open = False
        return dict(transaction.balances)

    def get_open_channel(self, channel_id: ChannelId) -> Channel:
        if channel_id not in self.channels:
            raise ValueError("canale sconosciuto")

        channel = self.channels[channel_id]
        if not channel.is_open:
            raise ValueError("canale gia' chiuso")
        return channel

    def get_commitment_transaction(
        self, channel: Channel, transaction_id: TransactionId
    ) -> CommitmentTransaction:
        for transaction in channel.commitments:
            if transaction.transaction_id == transaction_id:
                return transaction
        raise ValueError("commitment transaction sconosciuta")

    def validate_commitment_balances(self, channel: Channel, balances: Balances):
        if set(balances) != set(channel.participants):
            raise ValueError(
                "i balances devono contenere esattamente i partecipanti del canale"
            )
        if any(amount < 0 for amount in balances.values()):
            raise ValueError("i balances non possono essere negativi")
        if sum(balances.values()) != channel.capacity:
            raise ValueError("stato del canale incoerente")
