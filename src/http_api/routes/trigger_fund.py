import json

from commitment_transaction import CommitmentTransaction
from funding_transaction import Contribution, create_funding_transaction
from node import Channel, LightningNode

from ..client import NetworkClient


async def run(node: LightningNode, own_amount: int, peer_amount: int, peer_url: str):
    peer_url = peer_url.rstrip("/")
    peer_key = await NetworkClient.fetch_public_key(peer_url)

    funding = create_funding_transaction(
        Contribution(node.public_key, int(own_amount)),
        Contribution(peer_key, int(peer_amount)),
    )
    own_secret = node.generate_secret()
    own_hash = node.hash_sha256(own_secret)

    payload = {
        "funding": json.loads(funding.serialize().decode()),
        "initial_hash": own_hash,
    }
    response = await NetworkClient.post(f"{peer_url}/funding", payload)
    peer_hash = response["initial_hash"]

    peer_commitment = CommitmentTransaction(
        funding_id=funding.id,
        tx_index=0,
        owner=peer_key,
        own_amount=int(peer_amount),
        peer_amount=int(own_amount),
        revocation_hash=peer_hash,
    )
    complete_response = await NetworkClient.post(
        f"{peer_url}/complete-funding",
        {
            "funding_id": funding.id,
            "signature": peer_commitment.sign(node.private_key),
        },
    )

    channel = Channel(funding=funding, current_index=0)
    channel.own_secrets[0] = own_secret
    channel.peer_hashes[0] = peer_hash

    own_commitment = CommitmentTransaction(
        funding_id=funding.id,
        tx_index=0,
        owner=node.public_key,
        own_amount=int(own_amount),
        peer_amount=int(peer_amount),
        revocation_hash=own_hash,
    )
    if not own_commitment.verify(peer_key, complete_response["signature"]):
        raise ValueError("La firma ricevuta dal peer non è valida")

    own_commitment.signatures = {peer_key: complete_response["signature"]}
    channel.commitments[0] = own_commitment
    node.channels[funding.id] = channel
    return funding.id
