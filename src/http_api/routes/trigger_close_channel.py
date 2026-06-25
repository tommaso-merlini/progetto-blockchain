from lightningnetwork import LightningNode

from ..blockchain_client import MockBlockchainClient


async def run(node: LightningNode, funding_id: str, tx_index: int) -> dict:
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

    commitment.signatures[node.public_key] = commitment.sign(node.private_key)
    return await MockBlockchainClient.publish_close(commitment)
