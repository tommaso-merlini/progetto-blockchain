from dataclasses import dataclass, field
import hashlib
import secrets

from domain_types import ActorId, ActorName, PublicKey, SecretKey


@dataclass(frozen=True)
class Actor:
    actor_id: ActorId
    name: ActorName
    public_key: PublicKey
    secret_key: SecretKey = field(repr=False)


class Actors:
    def __init__(self):
        self.actors: list[Actor] = []

    def create_actor(self, actor_id: ActorId, name: ActorName | None = None) -> Actor:
        secret_key: SecretKey = secrets.token_hex(32)
        public_key: PublicKey = hashlib.sha256(secret_key.encode()).hexdigest()

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
