import json

from node import LightningNode


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        channel = node.channels[data["funding_id"]]
        old_index = data["tx_index"]

        if node.hash_sha256(data["secret"]) != channel.peer_hashes[old_index]:
            raise ValueError("Il segreto di revoca non corrisponde all'hash registrato")

        channel.revoked_peer_secrets[old_index] = data["secret"]
        old_own_secret = channel.own_secrets[old_index]
        channel.current_index += 1
        channel.pending_update = None

        return 200, json.dumps({"secret": old_own_secret}).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
