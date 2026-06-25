from lightningnetwork import LightningNode, validate_channel_balances

from ..client import NetworkClient


async def run(
    node: LightningNode,
    funding_id: str,
    new_own: int,
    new_peer: int,
    peer_url: str,
    own_url: str | None = None,
):
    peer_url = peer_url.rstrip("/")
    if own_url is not None:
        own_url = own_url.rstrip("/")
    channel = node.channels[funding_id]
    next_index = channel.current_index + 1

    if channel.pending_update is not None:
        raise ValueError("Esiste gia' una proposta pendente per questo canale")

    new_own, new_peer = validate_channel_balances(
        new_own, new_peer, channel.funding.output.amount
    )

    next_secret = node.generate_secret()
    own_hash = node.hash_sha256(next_secret)

    proposal_payload = {
        "funding_id": funding_id,
        "own_amount": new_own,
        "peer_amount": new_peer,
        "next_hash": own_hash,
    }
    if own_url:
        proposal_payload["peer_url"] = own_url
    proposal_response = await NetworkClient.post(
        f"{peer_url}/propose-update", proposal_payload
    )

    channel.peer_url = peer_url
    channel.own_secrets[next_index] = next_secret
    channel.peer_hashes[next_index] = proposal_response["next_hash"]
    channel.pending_update = {
        "role": "proposer",
        "next_index": next_index,
        "own_amount": new_own,
        "peer_amount": new_peer,
        "peer_url": peer_url,
    }
