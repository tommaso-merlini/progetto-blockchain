from dataclasses import dataclass
from collections.abc import Iterable
import hashlib
import json

from domain_types import Address, Money, PublicKey, Signature, Threshold


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
        signatures: Iterable[Signature],
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
        self, multi_sig_address: MultiSigAddress, signatures: Iterable[Signature]
    ) -> bool:
        valid_signers = set(signatures).intersection(multi_sig_address.public_keys)
        return len(valid_signers) >= multi_sig_address.threshold

    def __str__(self):
        return str(self.addresses)
