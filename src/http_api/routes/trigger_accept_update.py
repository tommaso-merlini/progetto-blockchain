from commitment_transaction import CommitmentTransaction
from node import LightningNode

from ..client import NetworkClient


async def run(node: LightningNode, funding_id: str, peer_url: str):
    peer_url = peer_url.rstrip("/")
    channel = node.channels[funding_id]
    pending = channel.pending_update
    if not pending or pending.get("role") != "responder":
        raise ValueError("Nessuna proposta pendente da accettare per questo canale")

    old_index = channel.current_index
    next_index = old_index + 1
    if pending.get("next_index") != next_index:
        raise ValueError("Indice della proposta pendente non coerente")

    peer_key = channel.funding.get_peer_contribution(node.public_key).public_key
    own_hash = node.hash_sha256(channel.own_secrets[next_index])

    signature_request = {
        "funding_id": funding_id,
        "next_hash": own_hash,
    }
    signature_response = await NetworkClient.post(
        f"{peer_url}/sign-pending-update", signature_request
    )

    own_commitment = CommitmentTransaction(
        funding_id=funding_id,
        tx_index=next_index,
        owner=node.public_key,
        own_amount=pending["peer_amount"],
        peer_amount=pending["own_amount"],
        revocation_hash=own_hash,
    )
    if not own_commitment.verify(peer_key, signature_response["signature"]):
        raise ValueError("La firma del peer sulla proposta non è valida")

    own_commitment.signatures = {peer_key: signature_response["signature"]}
    channel.commitments[next_index] = own_commitment

    peer_commitment = CommitmentTransaction(
        funding_id=funding_id,
        tx_index=next_index,
        owner=peer_key,
        own_amount=pending["own_amount"],
        peer_amount=pending["peer_amount"],
        revocation_hash=channel.peer_hashes[next_index],
    )
    complete_payload = {
        "funding_id": funding_id,
        "tx_index": old_index,
        "secret": channel.own_secrets[old_index],
        "signature": peer_commitment.sign(node.private_key),
    }
    complete_response = await NetworkClient.post(
        f"{peer_url}/complete-update", complete_payload
    )

    if node.hash_sha256(complete_response["secret"]) != channel.peer_hashes[old_index]:
        raise ValueError("Il segreto di revoca ricevuto dal peer non è corretto")

    channel.revoked_peer_secrets[old_index] = complete_response["secret"]
    channel.current_index = next_index
    channel.pending_update = None
