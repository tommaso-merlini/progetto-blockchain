from lightningnetwork import CommitmentTransaction, LightningNode

from ..client import NetworkClient


async def run(
    node: LightningNode, funding_id: str, new_own: int, new_peer: int, peer_url: str
):
    peer_url = peer_url.rstrip("/")
    channel = node.channels[funding_id]
    next_index = channel.current_index + 1
    peer_key = channel.funding.get_peer_contribution(node.public_key).public_key

    next_secret = node.generate_secret()
    own_hash = node.hash_sha256(next_secret)

    proposal_payload = {
        "funding_id": funding_id,
        "own_amount": int(new_own),
        "peer_amount": int(new_peer),
        "next_hash": own_hash,
    }
    proposal_response = await NetworkClient.post(
        f"{peer_url}/propose-update", proposal_payload
    )
    channel.peer_hashes[next_index] = proposal_response["next_hash"]

    peer_commitment = CommitmentTransaction(
        funding_id=funding_id,
        tx_index=next_index,
        owner=peer_key,
        own_amount=int(new_peer),
        peer_amount=int(new_own),
        revocation_hash=proposal_response["next_hash"],
    )

    signature_payload = {
        "funding_id": funding_id,
        "signature": peer_commitment.sign(node.private_key),
    }
    signature_response = await NetworkClient.post(
        f"{peer_url}/sign-update", signature_payload
    )

    own_commitment = CommitmentTransaction(
        funding_id=funding_id,
        tx_index=next_index,
        owner=node.public_key,
        own_amount=int(new_own),
        peer_amount=int(new_peer),
        revocation_hash=own_hash,
    )
    if not own_commitment.verify(peer_key, signature_response["signature"]):
        raise ValueError("La firma del peer sul nuovo stato non è valida")

    own_commitment.signatures = {peer_key: signature_response["signature"]}
    channel.commitments[next_index] = own_commitment

    old_index = channel.current_index
    revocation_payload = {
        "funding_id": funding_id,
        "tx_index": old_index,
        "secret": channel.own_secrets[old_index],
    }
    revocation_response = await NetworkClient.post(
        f"{peer_url}/revoke-state", revocation_payload
    )

    if node.hash_sha256(revocation_response["secret"]) != channel.peer_hashes[
        old_index
    ]:
        raise ValueError("Il segreto di revoca ricevuto dal peer non è corretto")

    channel.revoked_peer_secrets[old_index] = revocation_response["secret"]
    channel.own_secrets[next_index] = next_secret
    channel.current_index = next_index
