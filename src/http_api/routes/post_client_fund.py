import json

from lightningnetwork import LightningNode

from . import trigger_fund


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        funding_id = await trigger_fund.run(
            node,
            data["own_amount"],
            data["peer_amount"],
            data["peer_url"],
        )
        return 200, json.dumps({"funding_id": funding_id}).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
