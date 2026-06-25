import json
from dataclasses import dataclass, field
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

@dataclass
class CommitmentTransaction:
    funding_id: str
    tx_index: int              
    owner: str                 
    own_amount: int            
    peer_amount: int           
    revocation_hash: str       
    signatures: dict[str, str] = field(default_factory=dict)

    def payload(self) -> bytes:
        data = {
            "funding_id": self.funding_id,
            "tx_index": self.tx_index,
            "owner": self.owner,
            "own_amount": self.own_amount,
            "peer_amount": self.peer_amount,
            "revocation_hash": self.revocation_hash,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    def sign(self, private_key: Ed25519PrivateKey) -> str:
        return private_key.sign(self.payload()).hex()

    def verify(self, public_key: str, signature: str) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key)).verify(
                bytes.fromhex(signature), self.payload()
            )
            return True
        except (InvalidSignature, ValueError):
            return False

    def to_dict(self) -> dict:
        return {
            "funding_id": self.funding_id,
            "tx_index": self.tx_index,
            "owner": self.owner,
            "own_amount": self.own_amount,
            "peer_amount": self.peer_amount,
            "revocation_hash": self.revocation_hash,
            "signatures": dict(self.signatures),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CommitmentTransaction":
        commitment = cls(
            funding_id=data["funding_id"],
            tx_index=data["tx_index"],
            owner=data["owner"],
            own_amount=data["own_amount"],
            peer_amount=data["peer_amount"],
            revocation_hash=data["revocation_hash"],
        )
        commitment.signatures = dict(data.get("signatures", {}))
        return commitment
