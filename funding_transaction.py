import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True, order=True)
class Contribution:
    public_key: str
    amount: int


@dataclass(frozen=True)
class MultisigOutput:
    amount: int
    public_keys: tuple[str, str]
    required_signatures: int = 2


@dataclass(frozen=True)
class FundingTransaction:
    contributions: tuple[Contribution, Contribution]
    output: MultisigOutput

    def serialize(self) -> bytes:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()

    @property
    def id(self) -> str:
        return hashlib.sha256(self.serialize()).hexdigest()


def create_funding_transaction(
    own: Contribution,
    peer: Contribution,
) -> FundingTransaction:
    if own.amount < 0 or peer.amount < 0:
        raise ValueError("contributions cannot be negative")
    if own.public_key == peer.public_key:
        raise ValueError("public keys must be different")

    contributions = tuple(sorted((own, peer)))
    public_keys = tuple(item.public_key for item in contributions)
    output = MultisigOutput(own.amount + peer.amount, public_keys)
    return FundingTransaction(contributions, output)
