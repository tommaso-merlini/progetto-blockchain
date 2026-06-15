from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from domain_types import (
    Address,
    Balances,
    ChannelId,
    Money,
    PublicKey,
    RevocationHash,
    RevocationSecret,
    Signature,
    Threshold,
    TransactionId,
)


@dataclass
class PendingCommitmentClose:
    channel_id: ChannelId
    transaction_id: TransactionId
    balances: Balances
    broadcaster: PublicKey
    revocation_hashes: dict[PublicKey, RevocationHash]
    published_at_height: int
    challenge_period: int


@dataclass
class MultiSigAddress:
    address: Address
    public_keys: tuple[PublicKey, ...]
    threshold: Threshold
    initial_balances: Balances
    balance: Money
    pending_close: PendingCommitmentClose | None = None
    settlement_balances: Balances = field(default_factory=dict)


class BlockChain:
    def __init__(self):
        self.addresses: dict[Address, MultiSigAddress] = {}
        self.block_height = 0

    def create_multi_sig_address(
        self, initial_balances: Balances, threshold: Threshold
    ) -> MultiSigAddress:
        if any(amount <= 0 for amount in initial_balances.values()):
            raise ValueError("ogni balance iniziale deve essere positivo")

        public_keys = tuple(sorted(initial_balances))
        if not public_keys:
            raise ValueError("servono almeno una public key")
        if threshold < 1:
            raise ValueError("la threshold deve essere almeno 1")
        if threshold > len(public_keys):
            raise ValueError("la threshold non puo' superare il numero di public key")

        address = self.derive_address(public_keys, threshold)
        multi_sig_address = MultiSigAddress(
            address,
            public_keys,
            threshold,
            dict(initial_balances),
            sum(initial_balances.values()),
        )
        self.addresses[address] = multi_sig_address
        return multi_sig_address

    def deposit(self, address: Address, amount: Money):
        if amount <= 0:
            raise ValueError("l'importo deve essere positivo")

        multi_sig_address = self.get_address(address)
        multi_sig_address.balance += amount

    def spend(
        self,
        from_address: Address,
        to_address: Address,
        amount: Money,
        payload: bytes,
        signatures: dict[PublicKey, Signature],
    ):
        if amount <= 0:
            raise ValueError("l'importo deve essere positivo")

        multi_sig_address = self.get_address(from_address)
        if amount > multi_sig_address.balance:
            raise ValueError("saldo insufficiente")
        if not self.has_enough_valid_signatures(multi_sig_address, payload, signatures):
            raise ValueError("firme valide insufficienti")

        multi_sig_address.balance -= amount

    @staticmethod
    def multisig_spend_payload(
        from_address: Address,
        outputs: Balances,
        metadata: dict[str, Any] | None = None,
    ) -> bytes:
        payload = {
            "from_address": from_address,
            "outputs": dict(outputs),
            "metadata": metadata or {},
        }
        return json.dumps(payload, sort_keys=True).encode()

    @staticmethod
    def revocation_hash(
        channel_id: ChannelId,
        transaction_id: TransactionId,
        owner: PublicKey,
        secret: RevocationSecret,
    ) -> RevocationHash:
        payload = {
            "channel_id": channel_id,
            "owner": owner,
            "secret": secret,
            "transaction_id": transaction_id,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def spend_multisig(
        self,
        from_address: Address,
        outputs: Balances,
        signatures: dict[PublicKey, Signature],
        metadata: dict[str, Any] | None = None,
    ):
        if any(amount < 0 for amount in outputs.values()):
            raise ValueError("gli output non possono essere negativi")

        multi_sig_address = self.get_address(from_address)
        if multi_sig_address.pending_close is not None:
            raise ValueError("multisig gia' in chiusura")

        amount = sum(outputs.values())
        payload = self.multisig_spend_payload(from_address, outputs, metadata)
        if amount != multi_sig_address.balance:
            raise ValueError("gli output devono spendere l'intero multisig")
        if not self.has_enough_valid_signatures(multi_sig_address, payload, signatures):
            raise ValueError("firme valide insufficienti")

        multi_sig_address.balance = 0
        multi_sig_address.settlement_balances = dict(outputs)

    def publish_commitment(
        self,
        from_address: Address,
        outputs: Balances,
        signatures: dict[PublicKey, Signature],
        metadata: dict[str, Any],
        broadcaster: PublicKey,
        revocation_hashes: dict[PublicKey, RevocationHash],
        challenge_period: int = 1,
    ) -> PendingCommitmentClose:
        if challenge_period < 0:
            raise ValueError("il challenge period non puo' essere negativo")
        if any(amount < 0 for amount in outputs.values()):
            raise ValueError("gli output non possono essere negativi")

        multi_sig_address = self.get_address(from_address)
        if multi_sig_address.pending_close is not None:
            raise ValueError("multisig gia' in chiusura")
        if broadcaster not in multi_sig_address.public_keys:
            raise ValueError("broadcaster non partecipante")
        if set(outputs) != set(multi_sig_address.public_keys):
            raise ValueError("gli output devono contenere tutti i partecipanti")
        if set(revocation_hashes) != set(multi_sig_address.public_keys):
            raise ValueError("mancano revocation hash")

        amount = sum(outputs.values())
        payload = self.multisig_spend_payload(from_address, outputs, metadata)
        if amount != multi_sig_address.balance:
            raise ValueError("gli output devono spendere l'intero multisig")
        if not self.has_enough_valid_signatures(multi_sig_address, payload, signatures):
            raise ValueError("firme valide insufficienti")

        pending_close = PendingCommitmentClose(
            channel_id=metadata["channel_id"],
            transaction_id=metadata["transaction_id"],
            balances=dict(outputs),
            broadcaster=broadcaster,
            revocation_hashes=dict(revocation_hashes),
            published_at_height=self.block_height,
            challenge_period=challenge_period,
        )
        multi_sig_address.balance = 0
        multi_sig_address.pending_close = pending_close
        return pending_close

    def punish_commitment(
        self,
        from_address: Address,
        punished_party: PublicKey,
        beneficiary: PublicKey,
        secret: RevocationSecret,
    ) -> Balances:
        multi_sig_address = self.get_address(from_address)
        pending_close = multi_sig_address.pending_close
        if pending_close is None:
            raise ValueError("nessuna chiusura pending")
        if punished_party != pending_close.broadcaster:
            raise ValueError("puoi punire solo chi ha pubblicato la commitment")
        if beneficiary not in multi_sig_address.public_keys:
            raise ValueError("beneficiario non partecipante")
        if beneficiary == punished_party:
            raise ValueError("il beneficiario deve essere la controparte")

        expected_hash = pending_close.revocation_hashes[punished_party]
        actual_hash = self.revocation_hash(
            pending_close.channel_id,
            pending_close.transaction_id,
            punished_party,
            secret,
        )
        if actual_hash != expected_hash:
            raise ValueError("revocation secret non valido")

        settlement = {beneficiary: sum(pending_close.balances.values())}
        multi_sig_address.pending_close = None
        multi_sig_address.settlement_balances = settlement
        return dict(settlement)

    def finalize_commitment(self, from_address: Address) -> Balances:
        multi_sig_address = self.get_address(from_address)
        pending_close = multi_sig_address.pending_close
        if pending_close is None:
            raise ValueError("nessuna chiusura pending")
        if self.block_height < (
            pending_close.published_at_height + pending_close.challenge_period
        ):
            raise ValueError("challenge period non ancora terminato")

        settlement = dict(pending_close.balances)
        multi_sig_address.pending_close = None
        multi_sig_address.settlement_balances = settlement
        return dict(settlement)

    def mine_blocks(self, count: int = 1):
        if count < 1:
            raise ValueError("devi minare almeno un blocco")
        self.block_height += count

    def derive_address(
        self, public_keys: tuple[PublicKey, ...], threshold: Threshold
    ) -> Address:
        payload = json.dumps(
            {"public_keys": public_keys, "threshold": threshold},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:40]

    def get_address(self, address: Address) -> MultiSigAddress:
        if address not in self.addresses:
            raise ValueError("address sconosciuto")
        return self.addresses[address]

    def has_enough_valid_signatures(
        self,
        multi_sig_address: MultiSigAddress,
        payload: bytes,
        signatures: dict[PublicKey, Signature],
    ) -> bool:
        valid_signers = set()
        for public_key, signature in signatures.items():
            if public_key not in multi_sig_address.public_keys:
                continue
            if self.is_valid_signature(public_key, payload, signature):
                valid_signers.add(public_key)
        return len(valid_signers) >= multi_sig_address.threshold

    def is_valid_signature(
        self, public_key: PublicKey, payload: bytes, signature: Signature
    ) -> bool:
        try:
            verifying_key = Ed25519PublicKey.from_public_bytes(
                bytes.fromhex(public_key)
            )
            verifying_key.verify(bytes.fromhex(signature), payload)
        except (ValueError, InvalidSignature):
            return False
        return True

    def __str__(self):
        return str(self.addresses)
