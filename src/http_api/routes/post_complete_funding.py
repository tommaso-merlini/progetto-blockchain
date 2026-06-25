import json

from lightningnetwork import Channel, CommitmentTransaction, LightningNode


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        funding_id = data["funding_id"]
        pending = node.pending_fundings[funding_id]
        funding = pending.funding

        peer_key = funding.get_peer_contribution(node.public_key).public_key
        own_amount = funding.get_own_contribution(node.public_key).amount
        peer_amount = funding.get_peer_contribution(node.public_key).amount
        own_hash = node.hash_sha256(pending.own_secret)

        own_commitment = CommitmentTransaction(
            funding_id=funding.id,
            tx_index=0,
            owner=node.public_key,
            own_amount=own_amount,
            peer_amount=peer_amount,
            revocation_hash=own_hash,
        )
        if not own_commitment.verify(peer_key, data["signature"]):
            raise ValueError("Firma iniziale del peer non valida")

        channel = Channel(funding=funding, current_index=0)
        channel.own_secrets[0] = pending.own_secret
        channel.peer_hashes[0] = pending.peer_hash
        own_commitment.signatures = {peer_key: data["signature"]}
        channel.commitments[0] = own_commitment
        node.channels[funding.id] = channel
        del node.pending_fundings[funding.id]

        peer_commitment = CommitmentTransaction(
            funding_id=funding.id,
            tx_index=0,
            owner=peer_key,
            own_amount=peer_amount,
            peer_amount=own_amount,
            revocation_hash=pending.peer_hash,
        )
        response = {
            "funding_id": funding.id,
            "signature": peer_commitment.sign(node.private_key),
        }
        return 200, json.dumps(response).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
