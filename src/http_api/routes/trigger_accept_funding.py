from lightningnetwork import Channel, CommitmentTransaction, LightningNode

from ..blockchain_client import MockBlockchainClient
from ..client import NetworkClient


async def run(node: LightningNode, funding_id: str, proposer_url: str):
    proposer_url = proposer_url.rstrip("/")
    pending = node.pending_fundings[funding_id]
    if pending.role != "responder":
        raise ValueError("Nessuna funding ricevuta da accettare per questo id")

    funding = pending.funding
    peer_key = funding.get_peer_contribution(node.public_key).public_key
    proposer_key = await NetworkClient.fetch_public_key(proposer_url)
    if proposer_key != peer_key:
        raise ValueError("La chiave pubblica del proponente non coincide con il funding")

    own_amount = funding.get_own_contribution(node.public_key).amount
    peer_amount = funding.get_peer_contribution(node.public_key).amount
    own_hash = node.hash_sha256(pending.own_secret)

    peer_commitment = CommitmentTransaction(
        funding_id=funding.id,
        tx_index=0,
        owner=peer_key,
        own_amount=peer_amount,
        peer_amount=own_amount,
        revocation_hash=pending.peer_hash,
    )
    complete_response = await NetworkClient.post(
        f"{proposer_url}/complete-funding",
        {
            "funding_id": funding.id,
            "signature": peer_commitment.sign(node.private_key),
        },
    )

    own_commitment = CommitmentTransaction(
        funding_id=funding.id,
        tx_index=0,
        owner=node.public_key,
        own_amount=own_amount,
        peer_amount=peer_amount,
        revocation_hash=own_hash,
    )
    if not own_commitment.verify(peer_key, complete_response["signature"]):
        raise ValueError("La firma ricevuta dal proponente non è valida")

    channel = Channel(funding=funding, current_index=0, peer_url=proposer_url)
    channel.own_secrets[0] = pending.own_secret
    channel.peer_hashes[0] = pending.peer_hash
    own_commitment.signatures = {peer_key: complete_response["signature"]}
    channel.commitments[0] = own_commitment
    await MockBlockchainClient.register_multisig(funding)
    node.channels[funding.id] = channel
    del node.pending_fundings[funding.id]
    return funding.id
