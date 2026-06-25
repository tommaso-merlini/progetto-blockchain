import json

from lightningnetwork import LightningNode

from . import trigger_close_channel


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        response = await trigger_close_channel.run_invalid_signature(
            node,
            data["funding_id"],
            data["tx_index"],
            data["mode"],
        )
        return 200, json.dumps(response).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
