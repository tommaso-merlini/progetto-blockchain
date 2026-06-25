import json

from lightningnetwork import LightningNode

from . import trigger_propose_update


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        await trigger_propose_update.run(
            node,
            data["funding_id"],
            data["own_amount"],
            data["peer_amount"],
            data["peer_url"],
        )
        return (
            200,
            json.dumps(
                {
                    "status": "pending",
                    "next_step": "peer must call /client/accept-update",
                }
            ).encode(),
            b"application/json",
        )
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
