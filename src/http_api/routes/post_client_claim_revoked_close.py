import json

from lightningnetwork import LightningNode

from ..blockchain_client import MockBlockchainClient


async def handle(node: LightningNode, body: bytes):
    try:
        data = json.loads(body)
        funding_id = data["funding_id"]
        if funding_id not in node.channels:
            raise ValueError("Canale non trovato")

        channel = node.channels[funding_id]
        multisig = await MockBlockchainClient.get_multisig_status(funding_id)
        pending_close = multisig.get("pending_close")
        if pending_close is None:
            raise ValueError("Nessuna chiusura pendente per questo funding")

        commitment = pending_close["commitment"]
        if commitment["owner"] == node.public_key:
            raise ValueError("Il nodo non puo' reclamare una propria close")

        tx_index = commitment["tx_index"]
        if type(tx_index) is not int:
            raise ValueError("L'indice della commitment deve essere un intero JSON")

        secret = channel.revoked_peer_secrets.get(tx_index)
        if secret is None:
            raise ValueError("Secret di revoca non disponibile per questo stato")
        if node.hash_sha256(secret) != commitment["revocation_hash"]:
            raise ValueError("Il secret locale non sblocca la close pendente")

        response = await MockBlockchainClient.claim_revoked_close(
            funding_id,
            node.public_key,
            secret,
        )
        del node.channels[funding_id]
        return 200, json.dumps(response).encode(), b"application/json"
    except Exception as e:
        return 400, json.dumps({"error": str(e)}).encode(), b"application/json"
