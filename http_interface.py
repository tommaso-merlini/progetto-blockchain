import json
import asyncio
from urllib.request import Request, urlopen

from funding_transaction import Contribution, create_funding_transaction
from commitment_transaction import CommitmentTransaction
from node import Channel, LightningNode

class NetworkClient:
    """Gestisce le richieste HTTP uscenti in modo non bloccante per l'event loop."""
    @staticmethod
    async def post(url: str, payload: dict) -> dict:
        def _sync_post():
            req = Request(
                url, 
                data=json.dumps(payload).encode(), 
                headers={"Content-Type": "application/json"}, 
                method="POST"
            )
            with urlopen(req, timeout=5) as response:
                return json.loads(response.read().decode())
        return await asyncio.to_thread(_sync_post)

    @staticmethod
    async def fetch_public_key(peer_url: str) -> str:
        def _sync_get():
            with urlopen(f"{peer_url.rstrip('/')}/public-key", timeout=3) as response:
                return response.read().decode().strip()
        return await asyncio.to_thread(_sync_get)


class HttpInterface:
    """Gestisce il server ASGI e mappa gli endpoint HTTP verso la logica del nodo."""
    def __init__(self, node: LightningNode):
        self.node = node
        self.routes = {
            ("GET", "/public-key"): self.handle_get_public_key,
            ("GET", "/status"): self.handle_get_status,
            ("POST", "/funding"): self.handle_post_funding,
            ("POST", "/propose-update"): self.handle_post_propose_update,
            ("POST", "/sign-update"): self.handle_post_sign_update,
            ("POST", "/revoke-state"): self.handle_post_revoke_state,
            ("POST", "/client/fund"): self.handle_client_fund,
            ("POST", "/client/update"): self.handle_client_update,
        }

    async def __call__(self, scope, receive, send):
        """Interfaccia di ingresso ASGI nativa richiesta da Uvicorn."""
        if scope["type"] != "http":
            return

        body = b""
        while (message := await receive())["type"] == "http.request":
            body += message.get("body", b"")
            if not message.get("more_body"):
                break

        method = scope["method"]
        path = scope["path"]
        handler = self.routes.get((method, path))

        if handler:
            status, response_body, content_type = await handler(body)
        else:
            status, response_body, content_type = 404, b"Not Found\n", b"text/plain"

        await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", content_type)]})
        await send({"type": "http.response.body", "body": response_body})

    # --- HANDLERS INBOUND (Server) ---

    async def handle_get_public_key(self, body: bytes):
        return 200, self.node.public_key.encode(), b"text/plain; charset=utf-8"

    async def handle_get_status(self, body: bytes):
        status_data = {}
        for channel_id, channel in self.node.channels.items():
            current_commitment = channel.commitments[channel.current_index]
            status_data[channel_id] = {
                "current_index": channel.current_index,
                "own_amount": current_commitment.own_amount,
                "peer_amount": current_commitment.peer_amount
            }
        return 200, json.dumps(status_data).encode(), b"application/json"

    async def handle_post_funding(self, body: bytes):
        try:
            data = json.loads(body)
            funding_data = data["funding"]
            contributions = [Contribution(**c) for c in funding_data["contributions"]]
            funding = create_funding_transaction(*contributions)
            
            peer_key = funding.get_peer_contribution(self.node.public_key).public_key
            bob_amount = funding.get_own_contribution(self.node.public_key).amount
            alice_amount = funding.get_peer_contribution(self.node.public_key).amount

            peer_commitment = CommitmentTransaction(
                funding_id=funding.id, tx_index=0, owner=self.node.public_key,
                own_amount=bob_amount, peer_amount=alice_amount, revocation_hash=data["initial_hash"]
            )
            if not peer_commitment.verify(peer_key, data["signature"]):
                raise ValueError("Firma iniziale del peer non valida")

            channel = Channel(funding=funding, current_index=0)
            initial_secret = self.node.generate_secret()
            channel.own_secrets[0] = initial_secret
            channel.peer_hashes[0] = data["initial_hash"]
            
            peer_commitment.signatures = {peer_key: data["signature"]}
            channel.commitments[0] = peer_commitment
            self.node.channels[funding.id] = channel

            alice_commitment = CommitmentTransaction(
                funding_id=funding.id, tx_index=0, owner=peer_key,
                own_amount=alice_amount, peer_amount=bob_amount, revocation_hash=data["initial_hash"]
            )

            response = {
                "funding_id": funding.id,
                "initial_hash": self.node.hash_sha256(initial_secret),
                "signature": alice_commitment.sign(self.node.private_key)
            }
            return 200, json.dumps(response).encode(), b"application/json"
        except Exception as e:
            return 400, json.dumps({"error": str(e)}).encode(), b"application/json"

    async def handle_post_propose_update(self, body: bytes):
        try:
            data = json.loads(body)
            channel = self.node.channels[data["funding_id"]]
            next_index = channel.current_index + 1
            
            if data["own_amount"] + data["peer_amount"] != channel.funding.output.amount:
                raise ValueError("I bilanci proposti violano la capacità del canale")

            channel.peer_hashes[next_index] = data["next_hash"]
            channel.pending_update = {"own_amount": data["own_amount"], "peer_amount": data["peer_amount"]}

            next_secret = self.node.generate_secret()
            channel.own_secrets[next_index] = next_secret
            return 200, json.dumps({"next_hash": self.node.hash_sha256(next_secret)}).encode(), b"application/json"
        except Exception as e:
            return 400, json.dumps({"error": str(e)}).encode(), b"application/json"

    async def handle_post_sign_update(self, body: bytes):
        try:
            data = json.loads(body)
            channel = self.node.channels[data["funding_id"]]
            next_index = channel.current_index + 1
            peer_key = channel.funding.get_peer_contribution(self.node.public_key).public_key

            own_commitment = CommitmentTransaction(
                funding_id=channel.funding.id, tx_index=next_index, owner=self.node.public_key,
                own_amount=channel.pending_update["peer_amount"], peer_amount=channel.pending_update["own_amount"],
                revocation_hash=self.node.hash_sha256(channel.own_secrets[next_index])
            )
            if not own_commitment.verify(peer_key, data["signature"]):
                raise ValueError("Firma di impegno non valida")

            own_commitment.signatures = {peer_key: data["signature"]}
            channel.commitments[next_index] = own_commitment

            peer_commitment = CommitmentTransaction(
                funding_id=channel.funding.id, tx_index=next_index, owner=peer_key,
                own_amount=channel.pending_update["own_amount"], peer_amount=channel.pending_update["peer_amount"],
                revocation_hash=channel.peer_hashes[next_index]
            )
            return 200, json.dumps({"signature": peer_commitment.sign(self.node.private_key)}).encode(), b"application/json"
        except Exception as e:
            return 400, json.dumps({"error": str(e)}).encode(), b"application/json"

    async def handle_post_revoke_state(self, body: bytes):
        try:
            data = json.loads(body)
            channel = self.node.channels[data["funding_id"]]
            old_index = data["tx_index"]
            
            if self.node.hash_sha256(data["secret"]) != channel.peer_hashes[old_index]:
                raise ValueError("Il segreto di revoca non corrisponde all'hash registrato")

            channel.revoked_peer_secrets[old_index] = data["secret"]
            old_own_secret = channel.own_secrets[old_index]
            channel.current_index += 1
            channel.pending_update = None

            return 200, json.dumps({"secret": old_own_secret}).encode(), b"application/json"
        except Exception as e:
            return 400, json.dumps({"error": str(e)}).encode(), b"application/json"

    # --- LOGICA AZIONI OUTBOUND (Client) ---

    async def handle_client_fund(self, body: bytes):
        try:
            data = json.loads(body)
            funding_id = await self.trigger_fund_logic(data["own_amount"], data["peer_amount"], data["peer_url"])
            return 200, json.dumps({"funding_id": funding_id}).encode(), b"application/json"
        except Exception as e:
            return 400, json.dumps({"error": str(e)}).encode(), b"application/json"

    async def handle_client_update(self, body: bytes):
        try:
            data = json.loads(body)
            await self.trigger_update_logic(data["funding_id"], data["own_amount"], data["peer_amount"], data["peer_url"])
            return 200, json.dumps({"status": "success"}).encode(), b"application/json"
        except Exception as e:
            return 400, json.dumps({"error": str(e)}).encode(), b"application/json"

    async def trigger_fund_logic(self, own_amount: int, peer_amount: int, peer_url: str) -> str:
        peer_url = peer_url.rstrip("/")
        peer_key = await NetworkClient.fetch_public_key(peer_url)
            
        funding = create_funding_transaction(
            Contribution(self.node.public_key, int(own_amount)), 
            Contribution(peer_key, int(peer_amount))
        )
        own_secret = self.node.generate_secret()
        own_hash = self.node.hash_sha256(own_secret)
        
        peer_commitment = CommitmentTransaction(
            funding_id=funding.id, tx_index=0, owner=peer_key,
            own_amount=int(peer_amount), peer_amount=int(own_amount), revocation_hash=own_hash
        )
        
        payload = {
            "funding": json.loads(funding.serialize().decode()), 
            "initial_hash": own_hash, 
            "signature": peer_commitment.sign(self.node.private_key)
        }
        response = await NetworkClient.post(f"{peer_url}/funding", payload)
        
        channel = Channel(funding=funding, current_index=0)
        channel.own_secrets[0] = own_secret
        channel.peer_hashes[0] = response["initial_hash"]
        
        own_commitment = CommitmentTransaction(
            funding_id=funding.id, tx_index=0, owner=self.node.public_key,
            own_amount=int(own_amount), peer_amount=int(peer_amount), revocation_hash=own_hash
        )
        if not own_commitment.verify(peer_key, response["signature"]):
            raise ValueError("La firma ricevuta dal peer non è valida")
            
        own_commitment.signatures = {peer_key: response["signature"]}
        channel.commitments[0] = own_commitment
        self.node.channels[funding.id] = channel
        return funding.id

    async def trigger_update_logic(self, funding_id: str, new_own: int, new_peer: int, peer_url: str):
        peer_url = peer_url.rstrip("/")
        channel = self.node.channels[funding_id]
        next_index = channel.current_index + 1
        peer_key = channel.funding.get_peer_contribution(self.node.public_key).public_key
        
        next_secret = self.node.generate_secret()
        own_hash = self.node.hash_sha256(next_secret)
        
        proposal_payload = {
            "funding_id": funding_id, 
            "own_amount": int(new_own), 
            "peer_amount": int(new_peer), 
            "next_hash": own_hash
        }
        proposal_response = await NetworkClient.post(f"{peer_url}/propose-update", proposal_payload)
        channel.peer_hashes[next_index] = proposal_response["next_hash"]
        
        peer_commitment = CommitmentTransaction(
            funding_id=funding_id, tx_index=next_index, owner=peer_key,
            own_amount=int(new_peer), peer_amount=int(new_own), revocation_hash=proposal_response["next_hash"]
        )
        
        signature_payload = {"funding_id": funding_id, "signature": peer_commitment.sign(self.node.private_key)}
        signature_response = await NetworkClient.post(f"{peer_url}/sign-update", signature_payload)
        
        own_commitment = CommitmentTransaction(
            funding_id=funding_id, tx_index=next_index, owner=self.node.public_key,
            own_amount=int(new_own), peer_amount=int(new_peer), revocation_hash=own_hash
        )
        if not own_commitment.verify(peer_key, signature_response["signature"]):
            raise ValueError("La firma del peer sul nuovo stato non è valida")
            
        own_commitment.signatures = {peer_key: signature_response["signature"]}
        channel.commitments[next_index] = own_commitment
        
        old_index = channel.current_index
        revocation_payload = {
            "funding_id": funding_id, 
            "tx_index": old_index, 
            "secret": channel.own_secrets[old_index]
        }
        revocation_response = await NetworkClient.post(f"{peer_url}/revoke-state", revocation_payload)
        
        if self.node.hash_sha256(revocation_response["secret"]) != channel.peer_hashes[old_index]:
            raise ValueError("Il segreto di revoca ricevuto dal peer non è corretto")
            
        channel.revoked_peer_secrets[old_index] = revocation_response["secret"]
        channel.own_secrets[next_index] = next_secret
        channel.current_index = next_index