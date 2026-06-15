from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from domain_types import ActorId, ActorName, PublicKey, SecretKey, Signature


@dataclass(frozen=True)
class Actor:
    actor_id: ActorId
    name: ActorName
    public_key: PublicKey
    secret_key: SecretKey = field(repr=False)

    def sign(self, payload: bytes) -> Signature:
        private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.secret_key))
        return private_key.sign(payload).hex()


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
