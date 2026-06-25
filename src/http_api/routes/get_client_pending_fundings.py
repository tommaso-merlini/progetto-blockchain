import json

from lightningnetwork import LightningNode


async def handle(node: LightningNode, _body: bytes):
    pending_data = {}
    for funding_id, pending in node.pending_fundings.items():
        own_amount = pending.funding.get_own_contribution(node.public_key).amount
        peer_amount = pending.funding.get_peer_contribution(node.public_key).amount
        pending_data[funding_id] = {
            "role": pending.role,
            "own_amount": own_amount,
            "peer_amount": peer_amount,
            "capacity": pending.funding.output.amount,
        }
        if pending.peer_url:
            pending_data[funding_id]["peer_url"] = pending.peer_url
    return 200, json.dumps(pending_data).encode(), b"application/json"
