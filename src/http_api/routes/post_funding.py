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
        funding = create_funding_transaction(*contributions)
        funding.get_own_contribution(node.public_key)
        funding.get_peer_contribution(node.public_key)

        initial_secret = node.generate_secret()
        node.pending_fundings[funding.id] = PendingFunding(
            funding=funding,
            own_secret=initial_secret,
            peer_hash=data["initial_hash"],
        )

        response = {
            "funding_id": funding.id,
            "initial_hash": node.hash_sha256(initial_secret),
        }
        return 200, json.dumps(response).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
