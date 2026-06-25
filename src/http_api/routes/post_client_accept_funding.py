import json

from lightningnetwork import LightningNode

from . import trigger_accept_funding


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        funding_id = await trigger_accept_funding.run(
            node,
            data["funding_id"],
            data["proposer_url"],
        )
        return (
            200,
            json.dumps({"status": "success", "funding_id": funding_id}).encode(),
            b"application/json",
        )
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
