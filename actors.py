from dataclasses import dataclass, field
import secrets

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from blockchain import BlockChain
from domain_types import (
    Address,
    ActorId,
    ActorName,
    Balances,
    ChannelId,
    Money,
    PublicKey,
    RevocationHash,
    RevocationSecret,
    SecretKey,
    Signature,
    TransactionId,
)
from lightning_network import Channel, CommitmentTransaction, LightningNetwork


@dataclass
class LocalChannelState:
    channel_id: ChannelId
    funding_address: Address
    participants: tuple[PublicKey, ...]
    counterparty: PublicKey
    capacity: Money
    next_transaction_id: TransactionId = 0
    current_commitment: CommitmentTransaction | None = None
    pending_commitment: CommitmentTransaction | None = None
    old_commitments: dict[TransactionId, CommitmentTransaction] = field(
        default_factory=dict
    )
    my_revocation_secrets: dict[TransactionId, RevocationSecret] = field(
        default_factory=dict
    )
    counterparty_revocation_secrets: dict[TransactionId, RevocationSecret] = field(
        default_factory=dict
    )


@dataclass
class Actor:
    actor_id: ActorId
    name: ActorName
    public_key: PublicKey
    secret_key: SecretKey = field(repr=False)
    revocation_secrets: dict[TransactionId, RevocationSecret] = field(
        default_factory=dict,
        repr=False,
    )
    channels: dict[ChannelId, LocalChannelState] = field(default_factory=dict)

    def sign(self, payload: bytes) -> Signature:
        private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.secret_key))
        return private_key.sign(payload).hex()

    def create_revocation_secret(self, transaction_id: TransactionId) -> RevocationSecret:
        secret = secrets.token_hex(32)
        self.revocation_secrets[transaction_id] = secret
        return secret

    def get_revocation_secret(self, transaction_id: TransactionId) -> RevocationSecret:
        return self.revocation_secrets[transaction_id]

    def create_revocation_hash(
        self,
        channel_id: ChannelId,
        transaction_id: TransactionId,
    ) -> RevocationHash:
        secret = self.create_revocation_secret(transaction_id)
        return BlockChain.revocation_hash(
            channel_id,
            transaction_id,
            self.public_key,
            secret,
        )

    def open_local_channel(self, channel: Channel, counterparty: PublicKey):
        if self.public_key not in channel.participants:
            raise ValueError("actor non partecipante")
        if counterparty not in channel.participants:
            raise ValueError("controparte non partecipante")
        if counterparty == self.public_key:
            raise ValueError("la controparte deve essere diversa dall'actor")

        self.channels[channel.channel_id] = LocalChannelState(
            channel_id=channel.channel_id,
            funding_address=channel.funding_address,
            participants=channel.participants,
            counterparty=counterparty,
            capacity=channel.capacity,
        )

    def propose_commitment(
        self,
        lightning_network: LightningNetwork,
        channel_id: ChannelId,
        balances: Balances,
        revocation_hashes: dict[PublicKey, RevocationHash],
    ) -> CommitmentTransaction:
        state = self.get_local_channel(channel_id)
        transaction_id = state.next_transaction_id
        transaction = lightning_network.create_commitment(
            channel_id,
            transaction_id,
            balances,
            revocation_hashes,
        )
        transaction.add_signature(self.public_key, self.sign(transaction.payload()))
        state.pending_commitment = transaction
        return transaction

    def receive_commitment_proposal(
        self,
        lightning_network: LightningNetwork,
        transaction: CommitmentTransaction,
        proposer: PublicKey,
    ) -> CommitmentTransaction:
        state = self.get_local_channel(transaction.channel_id)
        self._validate_counterparty(state, proposer)
        self._validate_expected_transaction_id(state, transaction)
        self._validate_commitment(lightning_network, state, transaction, proposer)

        transaction.add_signature(self.public_key, self.sign(transaction.payload()))
        self._accept_current_commitment(state, transaction)
        return transaction

    def receive_signed_commitment(
        self,
        lightning_network: LightningNetwork,
        transaction: CommitmentTransaction,
        signer: PublicKey,
    ):
        state = self.get_local_channel(transaction.channel_id)
        self._validate_counterparty(state, signer)
        self._validate_expected_transaction_id(state, transaction)
        self._validate_commitment(lightning_network, state, transaction, signer)
        self._accept_current_commitment(state, transaction)

    def reveal_previous_secret(
        self,
        channel_id: ChannelId,
        transaction_id: TransactionId,
    ) -> RevocationSecret:
        state = self.get_local_channel(channel_id)
        current = state.current_commitment
        if current is None or current.transaction_id <= transaction_id:
            raise ValueError("nessuna commitment successiva valida")
        if not self.has_valid_counterparty_signature(current):
            raise ValueError("commitment successiva senza firma della controparte")

        try:
            return state.my_revocation_secrets[transaction_id]
        except KeyError:
            raise ValueError("revocation secret sconosciuto")

    def receive_revocation_secret(
        self,
        transaction: CommitmentTransaction,
        owner: PublicKey,
        secret: RevocationSecret,
    ):
        state = self.get_local_channel(transaction.channel_id)
        self._validate_counterparty(state, owner)
        if owner not in transaction.revocation_hashes:
            raise ValueError("commitment senza revocation hash per owner")

        actual_hash = BlockChain.revocation_hash(
            transaction.channel_id,
            transaction.transaction_id,
            owner,
            secret,
        )
        if actual_hash != transaction.revocation_hashes[owner]:
            raise ValueError("revocation secret non valido")

        state.counterparty_revocation_secrets[transaction.transaction_id] = secret

    def get_counterparty_revocation_secret(
        self,
        channel_id: ChannelId,
        transaction_id: TransactionId,
    ) -> RevocationSecret:
        state = self.get_local_channel(channel_id)
        try:
            return state.counterparty_revocation_secrets[transaction_id]
        except KeyError:
            raise ValueError("revocation secret sconosciuto")

    def get_local_channel(self, channel_id: ChannelId) -> LocalChannelState:
        try:
            return self.channels[channel_id]
        except KeyError:
            raise ValueError("canale locale sconosciuto")

    def create_channel_revocation_hash(
        self,
        channel_id: ChannelId,
        transaction_id: TransactionId,
    ) -> RevocationHash:
        state = self.get_local_channel(channel_id)
        secret = self.create_revocation_secret(transaction_id)
        state.my_revocation_secrets[transaction_id] = secret
        return BlockChain.revocation_hash(
            channel_id, transaction_id, self.public_key, secret
        )

    def has_valid_counterparty_signature(
        self,
        transaction: CommitmentTransaction,
    ) -> bool:
        state = self.get_local_channel(transaction.channel_id)
        if state.counterparty not in transaction.signatures:
            return False
        return BlockChain().is_valid_signature(
            state.counterparty,
            transaction.payload(),
            transaction.signatures[state.counterparty],
        )

    def _accept_current_commitment(
        self,
        state: LocalChannelState,
        transaction: CommitmentTransaction,
    ):
        if state.current_commitment is not None:
            state.old_commitments[
                state.current_commitment.transaction_id
            ] = state.current_commitment
        state.current_commitment = transaction
        state.pending_commitment = None
        state.next_transaction_id = transaction.transaction_id + 1

    def _validate_commitment(
        self,
        lightning_network: LightningNetwork,
        state: LocalChannelState,
        transaction: CommitmentTransaction,
        required_signer: PublicKey,
    ):
        channel = lightning_network.get_open_channel(transaction.channel_id)
        if transaction.funding_address != state.funding_address:
            raise ValueError("funding address incoerente")
        if transaction.channel_id != state.channel_id:
            raise ValueError("canale incoerente")
        if set(transaction.revocation_hashes) != set(state.participants):
            raise ValueError("mancano revocation hash")
        lightning_network.validate_commitment_balances(channel, transaction.balances)
        if required_signer not in transaction.signatures:
            raise ValueError("firma della controparte mancante")
        if not lightning_network.blockchain.is_valid_signature(
            required_signer,
            transaction.payload(),
            transaction.signatures[required_signer],
        ):
            raise ValueError("firma della controparte non valida")

    def _validate_counterparty(self, state: LocalChannelState, public_key: PublicKey):
        if public_key != state.counterparty:
            raise ValueError("controparte inattesa")

    def _validate_expected_transaction_id(
        self,
        state: LocalChannelState,
        transaction: CommitmentTransaction,
    ):
        if transaction.transaction_id != state.next_transaction_id:
            raise ValueError("transaction id inatteso")


class Actors:
    def __init__(self):
        self.actors: list[Actor] = []

    def create_actor(self, actor_id: ActorId, name: ActorName | None = None) -> Actor:
        private_key = Ed25519PrivateKey.generate()
        secret_key: SecretKey = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        ).hex()
        public_key: PublicKey = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        ).hex()

        a = Actor(
            actor_id=actor_id,
            name=name or actor_id,
            public_key=public_key,
            secret_key=secret_key,
        )

        self.actors.append(a)

        return a

    def get_actor_by_id(self, actor_id: ActorId) -> Actor | None:
        for ac in self.actors:
            if ac.actor_id == actor_id:
                return ac
        return None
