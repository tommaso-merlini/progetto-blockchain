import json

from lightningnetwork import (
    Contribution,
    LightningNode,
    PendingFunding,
    create_funding_transaction,
)


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        funding_data = data["funding"]
        contributions = [Contribution(**c) for c in funding_data["contributions"]]
        funding = create_funding_transaction(
            *contributions,
            nonce=funding_data["nonce"],
        )
        funding.get_own_contribution(node.public_key)
        funding.get_peer_contribution(node.public_key)
        if funding.id in node.pending_fundings:
            raise ValueError("Esiste gia' una funding pendente con questo id")

        peer_url = data.get("peer_url")
        if peer_url is not None:
            peer_url = str(peer_url).rstrip("/")

        initial_secret = node.generate_secret()
        node.pending_fundings[funding.id] = PendingFunding(
            funding=funding,
            own_secret=initial_secret,
            peer_hash=data["initial_hash"],
            peer_url=peer_url,
            role="responder",
        )

        response = {
            "funding_id": funding.id,
            "initial_hash": node.hash_sha256(initial_secret),
        }
        return 200, json.dumps(response).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
