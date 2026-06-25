import json

from lightningnetwork import CommitmentTransaction, LightningNode


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        channel = node.channels[data["funding_id"]]
        next_index = channel.current_index + 1
        peer_key = channel.funding.get_peer_contribution(node.public_key).public_key

        own_commitment = CommitmentTransaction(
            funding_id=channel.funding.id,
            tx_index=next_index,
            owner=node.public_key,
            own_amount=channel.pending_update["peer_amount"],
            peer_amount=channel.pending_update["own_amount"],
            revocation_hash=node.hash_sha256(channel.own_secrets[next_index]),
        )
        if not own_commitment.verify(peer_key, data["signature"]):
            raise ValueError("Firma di impegno non valida")

        own_commitment.signatures = {peer_key: data["signature"]}
        channel.commitments[next_index] = own_commitment

        peer_commitment = CommitmentTransaction(
            funding_id=channel.funding.id,
            tx_index=next_index,
            owner=peer_key,
            own_amount=channel.pending_update["own_amount"],
            peer_amount=channel.pending_update["peer_amount"],
            revocation_hash=channel.peer_hashes[next_index],
        )
        return (
            200,
            json.dumps({"signature": peer_commitment.sign(node.private_key)}).encode(),
            b"application/json",
        )
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
