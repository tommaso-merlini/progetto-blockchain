import json

from lightningnetwork import LightningNode


async def handle(node: LightningNode, body: bytes):
    status_data = {}
    for channel_id, channel in node.channels.items():
        current_commitment = channel.commitments[channel.current_index]
        capacity = channel.funding.output.amount
        status_data[channel_id] = {
            "current_index": channel.current_index,
            "own_amount": current_commitment.own_amount,
            "peer_amount": current_commitment.peer_amount,
            "capacity": capacity,
            "commitments": [
                {
                    "tx_index": commitment.tx_index,
                    "own_amount": commitment.own_amount,
                    "peer_amount": commitment.peer_amount,
                    "capacity": capacity,
                    "is_current": tx_index == channel.current_index,
                }
                for tx_index, commitment in sorted(channel.commitments.items())
            ],
            "revoked_peer_state_indices": sorted(channel.revoked_peer_secrets),
        }
        if channel.peer_url:
            status_data[channel_id]["peer_url"] = channel.peer_url
        if channel.pending_update:
            pending = channel.pending_update
            role = pending.get("role", "responder")
            if role == "proposer":
                pending_own = pending["own_amount"]
                pending_peer = pending["peer_amount"]
            else:
                pending_own = pending["peer_amount"]
                pending_peer = pending["own_amount"]
            status_data[channel_id]["pending_update"] = {
                "role": role,
                "next_index": pending.get("next_index"),
                "own_amount": pending_own,
                "peer_amount": pending_peer,
            }
    return 200, json.dumps(status_data).encode(), b"application/json"
