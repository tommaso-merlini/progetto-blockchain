from lightningnetwork import LightningNode

from ..client import NetworkClient


async def run(
    node: LightningNode, funding_id: str, new_own: int, new_peer: int, peer_url: str
):
    peer_url = peer_url.rstrip("/")
    channel = node.channels[funding_id]
    next_index = channel.current_index + 1

    if channel.pending_update is not None:
        raise ValueError("Esiste gia' una proposta pendente per questo canale")

    if int(new_own) + int(new_peer) != channel.funding.output.amount:
        raise ValueError(
            f"I bilanci proposti violano la capacità del canale: "
            f"{new_own} + {new_peer} != {channel.funding.output.amount}"
        )

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

    channel.own_secrets[next_index] = next_secret
    channel.peer_hashes[next_index] = proposal_response["next_hash"]
    channel.pending_update = {
        "role": "proposer",
        "next_index": next_index,
        "own_amount": int(new_own),
        "peer_amount": int(new_peer),
        "peer_url": peer_url,
    }
