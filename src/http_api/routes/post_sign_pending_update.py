import json

from lightningnetwork import CommitmentTransaction, LightningNode


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        channel = node.channels[data["funding_id"]]
        pending = channel.pending_update
        if not pending or pending.get("role") != "proposer":
            raise ValueError("Nessuna proposta locale pendente da firmare")

        next_index = channel.current_index + 1
        if pending.get("next_index") != next_index:
            raise ValueError("Indice della proposta pendente non coerente")

        peer_key = channel.funding.get_peer_contribution(node.public_key).public_key
        next_hash = data["next_hash"]
        known_peer_hash = channel.peer_hashes.get(next_index)
        if known_peer_hash is not None and known_peer_hash != next_hash:
            raise ValueError("L'hash del peer non coincide con la proposta pendente")
        channel.peer_hashes[next_index] = next_hash

        peer_commitment = CommitmentTransaction(
            funding_id=channel.funding.id,
            tx_index=next_index,
            owner=peer_key,
            own_amount=pending["peer_amount"],
            peer_amount=pending["own_amount"],
            revocation_hash=next_hash,
        )
        return (
            200,
            json.dumps({"signature": peer_commitment.sign(node.private_key)}).encode(),
            b"application/json",
        )
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
