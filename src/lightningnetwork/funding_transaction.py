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

    def get_peer_contribution(self, own_public_key: str) -> Contribution:
        """Estrae in modo sicuro la contribuzione della controparte."""
        for contribution in self.contributions:
            if contribution.public_key != own_public_key:
                return contribution
        raise ValueError("Controparte non trovata nelle contribuzioni.")

    def get_own_contribution(self, own_public_key: str) -> Contribution:
        """Estrae in modo sicuro la contribuzione locale."""
        for contribution in self.contributions:
            if contribution.public_key == own_public_key:
                return contribution
        raise ValueError("Contribuzione locale non trovata nelle contribuzioni.")

def create_funding_transaction(own: Contribution, peer: Contribution) -> FundingTransaction:
    if own.amount < 0 or peer.amount < 0:
        raise ValueError("Le contribuzioni non possono essere negative")
    if own.public_key == peer.public_key:
        raise ValueError("Le chiavi pubbliche devono essere differenti")

    contributions = tuple(sorted((own, peer)))
    public_keys = tuple(item.public_key for item in contributions)
    output = MultisigOutput(own.amount + peer.amount, public_keys)
    return FundingTransaction(contributions, output)