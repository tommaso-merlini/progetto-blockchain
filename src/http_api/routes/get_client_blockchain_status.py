import json

from lightningnetwork import LightningNode

from ..blockchain_client import MockBlockchainClient


async def handle(node: LightningNode, body: bytes):
    try:
        response = await MockBlockchainClient.get_status()
        return 200, json.dumps(response).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
