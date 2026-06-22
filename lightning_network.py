from dataclasses import dataclass, field
from typing import Any

from blockchain import BlockChain
from domain_types import (
    Address,
    Balances,
    ChannelId,
    Money,
    PublicKey,
    RevocationHash,
    Signature,
    TransactionId,
)


@dataclass
class CommitmentTransaction:
    transaction_id: TransactionId
    channel_id: ChannelId
    funding_address: Address
    balances: Balances
    revocation_hashes: dict[PublicKey, RevocationHash]
    signatures: dict[PublicKey, Signature] = field(default_factory=dict)

    def payload_metadata(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "channel_id": self.channel_id,
            "revocation_hashes": self.revocation_hashes,
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
        transaction_id: TransactionId,
        balances: Balances,
        revocation_hashes: dict[PublicKey, RevocationHash] | None = None,
    ) -> CommitmentTransaction:
        channel = self.get_open_channel(channel_id)
        self.validate_commitment_balances(channel, balances)
        self.validate_revocation_hashes(channel, revocation_hashes)

        return CommitmentTransaction(
            transaction_id=transaction_id,
            channel_id=channel.channel_id,
            funding_address=channel.funding_address,
            balances=dict(balances),
            revocation_hashes=dict(revocation_hashes or {}),
        )

    def create_commitment(
        self,
        channel_id: ChannelId,
        transaction_id: TransactionId,
        balances: Balances,
        revocation_hashes: dict[PublicKey, RevocationHash] | None = None,
    ) -> CommitmentTransaction:
        return self.create_transaction(
            channel_id, transaction_id, balances, revocation_hashes
        )

    def publish_commitment(
        self,
        transaction: CommitmentTransaction,
        broadcaster: PublicKey,
        challenge_period: int = 1,
    ):
        channel_id = transaction.channel_id
        channel = self.get_open_channel(channel_id)
        funding_wallet = self.blockchain.get_address(channel.funding_address)

        if broadcaster not in channel.participants:
            raise ValueError("broadcaster non partecipante")
        if not transaction.revocation_hashes:
            raise ValueError("commitment senza revocation hash")
        if not self.blockchain.has_enough_valid_signatures(
            funding_wallet, transaction.payload(), transaction.signatures
        ):
            raise ValueError("la commitment transaction non e' firmata correttamente")

        self.validate_commitment_balances(channel, transaction.balances)
        pending_close = self.blockchain.publish_commitment(
            funding_wallet.address,
            transaction.balances,
            transaction.signatures,
            transaction.payload_metadata(),
            broadcaster,
            transaction.revocation_hashes,
            challenge_period,
        )
        channel.is_open = False
        return pending_close

    def close_channel(
        self,
        transaction: CommitmentTransaction,
    ) -> Balances:
        channel_id = transaction.channel_id
        channel = self.get_open_channel(channel_id)
        funding_wallet = self.blockchain.get_address(channel.funding_address)

        if not self.blockchain.has_enough_valid_signatures(
            funding_wallet, transaction.payload(), transaction.signatures
        ):
            raise ValueError("la commitment transaction non e' firmata correttamente")

        self.validate_commitment_balances(channel, transaction.balances)

        self.publish_commitment(
            transaction,
            broadcaster=channel.participants[0],
            challenge_period=0,
        )
        return self.blockchain.finalize_commitment(funding_wallet.address)

    def get_open_channel(self, channel_id: ChannelId) -> Channel:
        if channel_id not in self.channels:
            raise ValueError("canale sconosciuto")

        channel = self.channels[channel_id]
        if not channel.is_open:
            raise ValueError("canale gia' chiuso")
        return channel

    def validate_commitment_balances(self, channel: Channel, balances: Balances):
        if set(balances) != set(channel.participants):
            raise ValueError(
                "i balances devono contenere esattamente i partecipanti del canale"
            )
        if any(amount < 0 for amount in balances.values()):
            raise ValueError("i balances non possono essere negativi")
        if sum(balances.values()) != channel.capacity:
            raise ValueError("stato del canale incoerente")

    def validate_revocation_hashes(
        self,
        channel: Channel,
        revocation_hashes: dict[PublicKey, RevocationHash] | None,
    ):
        if revocation_hashes is None:
            return
        if set(revocation_hashes) != set(channel.participants):
            raise ValueError("mancano revocation hash")
