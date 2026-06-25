import json

from lightningnetwork import (
    Contribution,
    LightningNode,
    PendingFunding,
    create_funding_transaction,
)

from ..client import NetworkClient


async def run(
    node: LightningNode,
    own_amount: int,
    peer_amount: int,
    peer_url: str,
    own_url: str | None = None,
):
    peer_url = peer_url.rstrip("/")
    if own_url is not None:
        own_url = own_url.rstrip("/")
    peer_key = await NetworkClient.fetch_public_key(peer_url)

    funding = create_funding_transaction(
        Contribution(node.public_key, int(own_amount)),
        Contribution(peer_key, int(peer_amount)),
    )
    if funding.id in node.pending_fundings:
        raise ValueError("Esiste gia' una funding pendente con questo id")

    own_secret = node.generate_secret()
    own_hash = node.hash_sha256(own_secret)

    payload = {
        "funding": json.loads(funding.serialize().decode()),
        "initial_hash": own_hash,
    }
    if own_url:
        payload["peer_url"] = own_url
    response = await NetworkClient.post(f"{peer_url}/funding", payload)
    if response["funding_id"] != funding.id:
        raise ValueError("Il peer ha risposto con un funding id inatteso")
    peer_hash = response["initial_hash"]

    node.pending_fundings[funding.id] = PendingFunding(
        funding=funding,
        own_secret=own_secret,
        peer_hash=peer_hash,
        peer_url=peer_url,
        role="proposer",
    )
    return funding.id
