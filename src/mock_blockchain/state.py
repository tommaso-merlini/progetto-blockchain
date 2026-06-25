import json
import hashlib
from dataclasses import dataclass

from lightningnetwork import (
    CommitmentTransaction,
    Contribution,
    FundingTransaction,
    create_funding_transaction,
    validate_channel_balances,
)


CHALLENGE_PERIOD_BLOCKS = 3


@dataclass
class MultisigRecord:
    funding: FundingTransaction
    spent: bool = False


@dataclass
class PendingClose:
    commitment: CommitmentTransaction
    published_at_block: int
    deadline_block: int


def funding_from_dict(data: dict) -> FundingTransaction:
    contributions = [Contribution(**item) for item in data["contributions"]]
    return create_funding_transaction(*contributions, nonce=data["nonce"])


class MockBlockchain:
    def __init__(self):
        self.block_number = 0
        self.multisigs: dict[str, MultisigRecord] = {}
        self.pending_closes: dict[str, PendingClose] = {}
        self.balances: dict[str, int] = {}

    def mine_block(self) -> int:
        self.block_number += 1
        return self.block_number

    def add_multisig(self, funding: FundingTransaction) -> str:
        existing = self.multisigs.get(funding.id)
        if existing is not None:
            if existing.funding.serialize() != funding.serialize():
                raise ValueError("Funding id gia' registrato con dati diversi")
            return funding.id

        self.multisigs[funding.id] = MultisigRecord(funding=funding)
        for public_key in funding.output.public_keys:
            self.balances.setdefault(public_key, 0)
        return funding.id

    def publish_close(self, commitment: CommitmentTransaction) -> PendingClose:
        funding_id = commitment.funding_id
        record = self.multisigs.get(funding_id)
        if record is None:
            raise ValueError("Multisig non trovato sulla blockchain")
        if record.spent:
            raise ValueError("Multisig gia' speso")
        if funding_id in self.pending_closes:
            raise ValueError("Canale gia' in chiusura")

        funding = record.funding
        public_keys = funding.output.public_keys
        if commitment.owner not in public_keys:
            raise ValueError("Owner della commitment non appartiene al multisig")
        if type(commitment.tx_index) is not int:
            raise ValueError("L'indice della commitment deve essere un intero JSON")
        validate_channel_balances(
            commitment.own_amount,
            commitment.peer_amount,
            funding.output.amount,
        )

        missing_signers = [
            public_key
            for public_key in public_keys
            if public_key not in commitment.signatures
        ]
        if missing_signers:
            raise ValueError("La close transaction deve avere entrambe le firme")

        for public_key in public_keys:
            signature = commitment.signatures[public_key]
            if not commitment.verify(public_key, signature):
                raise ValueError("Firma non valida sulla close transaction")

        pending_close = PendingClose(
            commitment=commitment,
            published_at_block=self.block_number,
            deadline_block=self.block_number + CHALLENGE_PERIOD_BLOCKS,
        )
        self.pending_closes[funding_id] = pending_close
        return pending_close

    def finalize_close(self, funding_id: str) -> dict:
        pending = self.pending_closes.get(funding_id)
        if pending is None:
            raise ValueError("Nessuna chiusura pendente per questo funding")
        if self.block_number < pending.deadline_block:
            raise ValueError("Periodo di contestazione non ancora concluso")

        record = self.multisigs[funding_id]
        if record.spent:
            raise ValueError("Multisig gia' speso")

        commitment = pending.commitment
        owner = commitment.owner
        peer = next(
            public_key
            for public_key in record.funding.output.public_keys
            if public_key != owner
        )
        self.balances[owner] = self.balances.get(owner, 0) + commitment.own_amount
        self.balances[peer] = self.balances.get(peer, 0) + commitment.peer_amount
        record.spent = True
        del self.pending_closes[funding_id]
        return {
            "funding_id": funding_id,
            "owner": owner,
            "peer": peer,
            "owner_amount": commitment.own_amount,
            "peer_amount": commitment.peer_amount,
        }

    def claim_revoked_close(self, funding_id: str, claimant: str, secret: str) -> dict:
        pending = self.pending_closes.get(funding_id)
        if pending is None:
            raise ValueError("Nessuna chiusura pendente per questo funding")

        record = self.multisigs[funding_id]
        if record.spent:
            raise ValueError("Multisig gia' speso")

        commitment = pending.commitment
        public_keys = record.funding.output.public_keys
        if claimant not in public_keys:
            raise ValueError("Il claimant non appartiene al multisig")
        if claimant == commitment.owner:
            raise ValueError(
                "L'owner della commitment non puo' reclamare la propria close"
            )

        expected_hash = hashlib.sha256(secret.encode()).hexdigest()
        if expected_hash != commitment.revocation_hash:
            raise ValueError("Secret di revoca non valido per la close pendente")

        claimed_amount = record.funding.output.amount
        self.balances[claimant] = self.balances.get(claimant, 0) + claimed_amount
        record.spent = True
        del self.pending_closes[funding_id]
        return {
            "funding_id": funding_id,
            "claimant": claimant,
            "owner": commitment.owner,
            "claimed_amount": claimed_amount,
        }

    def multisig_status(self, funding_id: str) -> dict:
        record = self.multisigs.get(funding_id)
        if record is None:
            raise ValueError("Multisig non trovato sulla blockchain")
        pending = self.pending_closes.get(funding_id)
        return {
            "funding_id": funding_id,
            "funding": json.loads(record.funding.serialize().decode()),
            "spent": record.spent,
            "pending_close": self._pending_close_to_dict(pending) if pending else None,
        }

    def status(self) -> dict:
        return {
            "block_number": self.block_number,
            "multisigs": {
                funding_id: self.multisig_status(funding_id)
                for funding_id in self.multisigs
            },
            "balances": dict(self.balances),
        }

    @staticmethod
    def _pending_close_to_dict(pending: PendingClose) -> dict:
        return {
            "commitment": pending.commitment.to_dict(),
            "published_at_block": pending.published_at_block,
            "deadline_block": pending.deadline_block,
        }
