import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Optional
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from funding_transaction import FundingTransaction, Contribution
from commitment_transaction import CommitmentTransaction

@dataclass
class Channel:
    funding: FundingTransaction
    current_index: int = 0
    commitments: dict[int, CommitmentTransaction] = field(default_factory=dict)
    own_secrets: dict[int, str] = field(default_factory=dict)
    peer_hashes: dict[int, str] = field(default_factory=dict)
    revoked_peer_secrets: dict[int, str] = field(default_factory=dict)
    pending_update: Optional[dict] = None

class LightningNode:
    def __init__(self):
        self.private_key = Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key().public_bytes_raw().hex()
        self.channels: dict[str, Channel] = {}

    @staticmethod
    def hash_sha256(secret: str) -> str:
        return hashlib.sha256(secret.encode()).hexdigest()

    def generate_secret(self) -> str:
        return secrets.token_hex(32)