import json

from lightningnetwork import LightningNode


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        channel = node.channels[data["funding_id"]]
        next_index = channel.current_index + 1

        if channel.pending_update is not None:
            raise ValueError("Esiste gia' una proposta pendente per questo canale")

        if data["own_amount"] + data["peer_amount"] != channel.funding.output.amount:
            raise ValueError("I bilanci proposti violano la capacità del canale")

        channel.peer_hashes[next_index] = data["next_hash"]
        channel.pending_update = {
            "role": "responder",
            "next_index": next_index,
            "own_amount": data["own_amount"],
            "peer_amount": data["peer_amount"],
        }

        next_secret = node.generate_secret()
        channel.own_secrets[next_index] = next_secret
        return (
            200,
            json.dumps({"next_hash": node.hash_sha256(next_secret)}).encode(),
            b"application/json",
        )
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
