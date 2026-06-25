import json

from lightningnetwork import CommitmentTransaction, LightningNode


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        channel = node.channels[data["funding_id"]]
        pending = channel.pending_update
        if not pending or pending.get("role") != "proposer":
            raise ValueError("Nessuna proposta locale pendente da completare")

        old_index = channel.current_index
        if data["tx_index"] != old_index:
            raise ValueError("Indice di revoca non coerente con lo stato corrente")

        next_index = old_index + 1
        peer_key = channel.funding.get_peer_contribution(node.public_key).public_key
        own_hash = node.hash_sha256(channel.own_secrets[next_index])

        own_commitment = CommitmentTransaction(
            funding_id=channel.funding.id,
            tx_index=next_index,
            owner=node.public_key,
            own_amount=pending["own_amount"],
            peer_amount=pending["peer_amount"],
            revocation_hash=own_hash,
        )
        if not own_commitment.verify(peer_key, data["signature"]):
            raise ValueError("La firma del peer sul nuovo stato non è valida")

        if node.hash_sha256(data["secret"]) != channel.peer_hashes[old_index]:
            raise ValueError("Il segreto di revoca del peer non è corretto")

        own_commitment.signatures = {peer_key: data["signature"]}
        channel.commitments[next_index] = own_commitment
        channel.revoked_peer_secrets[old_index] = data["secret"]
        old_own_secret = channel.own_secrets[old_index]
        channel.current_index = next_index
        channel.pending_update = None

        return 200, json.dumps({"secret": old_own_secret}).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
