from dataclasses import dataclass
from collections.abc import Iterable
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from domain_types import Address, Balances, Money, PublicKey, Signature, Threshold


@dataclass
class MultiSigAddress:
    address: Address
    public_keys: tuple[PublicKey, ...]
    threshold: Threshold
    balance: Money = 0


class BlockChain:
    def __init__(self):
        self.addresses: dict[Address, MultiSigAddress] = {}

    def create_multi_sig_address(
        self, public_keys: Iterable[PublicKey], threshold: Threshold
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
        if not self.has_enough_valid_signatures(
            multi_sig_address, payload, signatures
        ):
            raise ValueError("firme valide insufficienti")

        multi_sig_address.balance -= amount
        print(f"sent {amount} from {from_address} to {to_address}")

    @staticmethod
    def multisig_spend_payload(
        from_address: Address,
        outputs: Balances,
        metadata: dict[str, int] | None = None,
    ) -> bytes:
        payload = {
            "from_address": from_address,
            "outputs": dict(outputs),
            "metadata": metadata or {},
        }
        return json.dumps(payload, sort_keys=True).encode()

    def spend_multisig(
        self,
        from_address: Address,
        outputs: Balances,
        signatures: dict[PublicKey, Signature],
        metadata: dict[str, int] | None = None,
    ):
        if any(amount < 0 for amount in outputs.values()):
            raise ValueError("gli output non possono essere negativi")

        multi_sig_address = self.get_address(from_address)
        amount = sum(outputs.values())
        payload = self.multisig_spend_payload(from_address, outputs, metadata)
        if amount != multi_sig_address.balance:
            raise ValueError("gli output devono spendere l'intero multisig")
        if not self.has_enough_valid_signatures(
            multi_sig_address, payload, signatures
        ):
            raise ValueError("firme valide insufficienti")

        multi_sig_address.balance = 0
        print(f"sent {dict(outputs)} from {from_address}")

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
            verifying_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key))
            verifying_key.verify(bytes.fromhex(signature), payload)
        except (ValueError, InvalidSignature):
            return False
        return True

    def __str__(self):
        return str(self.addresses)
