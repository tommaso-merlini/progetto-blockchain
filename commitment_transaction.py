import json
from dataclasses import asdict, dataclass, field

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from funding_transaction import Contribution, FundingTransaction


@dataclass
class CommitmentTransaction:
    funding_id: str
    owner: str
    balances: tuple[Contribution, Contribution]
    signatures: dict[str, str] = field(default_factory=dict)

    def payload(self) -> bytes:
        data = {
            "funding_id": self.funding_id,
            "owner": self.owner,
            "balances": self.balances,
        }
        return json.dumps(
            data, default=asdict, sort_keys=True, separators=(",", ":")
        ).encode()

    def sign(self, key: Ed25519PrivateKey) -> str:
        return key.sign(self.payload()).hex()

    def verify(self, public_key: str, signature: str) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
                bytes.fromhex(signature), self.payload()
            )
            return True
        except (InvalidSignature, ValueError):
            return False


def create_commitment(funding: FundingTransaction, owner: str) -> CommitmentTransaction:
    if owner not in (item.public_key for item in funding.contributions):
        raise ValueError("commitment owner is not a channel participant")
    return CommitmentTransaction(funding.id, owner, funding.contributions)
