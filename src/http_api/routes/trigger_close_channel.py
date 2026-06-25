from lightningnetwork import CommitmentTransaction, LightningNode

from ..blockchain_client import MockBlockchainClient

INVALID_CLOSE_SIGNATURE_MODES = {
    "missing_peer_signature",
    "fake_peer_signature",
}


def _get_close_commitment(
    node: LightningNode, funding_id: str, tx_index: int
) -> CommitmentTransaction:
    if type(tx_index) is not int:
        raise ValueError("L'indice della commitment deve essere un intero JSON")
    if funding_id not in node.channels:
        raise ValueError("Canale non trovato")

    channel = node.channels[funding_id]
    if tx_index > channel.current_index:
        raise ValueError("Non puoi chiudere con una commitment futura")
    if tx_index not in channel.commitments:
        raise ValueError("Commitment non trovata per l'indice richiesto")

    commitment = channel.commitments[tx_index]
    if commitment.funding_id != funding_id:
        raise ValueError("La commitment non appartiene a questo funding")
    if commitment.owner != node.public_key:
        raise ValueError("Il nodo puo' pubblicare solo una propria commitment")

    return commitment


def _get_peer_public_key(node: LightningNode, funding_id: str) -> str:
    channel = node.channels[funding_id]
    peers = [
        public_key
        for public_key in channel.funding.output.public_keys
        if public_key != node.public_key
    ]
    if len(peers) != 1:
        raise ValueError("Il canale deve avere esattamente un peer")
    return peers[0]


async def run(node: LightningNode, funding_id: str, tx_index: int) -> dict:
    commitment = _get_close_commitment(node, funding_id, tx_index)
    commitment.signatures[node.public_key] = commitment.sign(node.private_key)
    return await MockBlockchainClient.publish_close(commitment)


async def run_invalid_signature(
    node: LightningNode, funding_id: str, tx_index: int, mode: str
) -> dict:
    if mode not in INVALID_CLOSE_SIGNATURE_MODES:
        raise ValueError("Modalita' di firma non valida")

    stored_commitment = _get_close_commitment(node, funding_id, tx_index)
    commitment = CommitmentTransaction.from_dict(stored_commitment.to_dict())
    commitment.signatures[node.public_key] = commitment.sign(node.private_key)

    peer_public_key = _get_peer_public_key(node, funding_id)
    if mode == "missing_peer_signature":
        commitment.signatures.pop(peer_public_key, None)
    else:
        commitment.signatures[peer_public_key] = "00" * 64

    return await MockBlockchainClient.publish_close(commitment)
