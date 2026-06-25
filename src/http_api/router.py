from lightningnetwork import LightningNode

from .routes import (
    get_client_blockchain_multisig,
    get_client_blockchain_status,
    get_client_pending_fundings,
    get_public_key,
    get_status,
    post_client_accept_funding,
    post_client_accept_update,
    post_client_close_channel,
    post_client_claim_revoked_close,
    post_client_finalize_close,
    post_client_fund,
    post_client_invalid_close_channel,
    post_client_propose_update,
    post_complete_funding,
    post_complete_update,
    post_funding,
    post_propose_update,
    post_revoke_state,
    post_sign_pending_update,
)


class HttpInterface:
    """Router ASGI con dispatch esplicito degli endpoint HTTP."""

    def __init__(self, node: LightningNode):
        self.node = node

    async def dispatch(self, method: str, path: str, body: bytes):
        if method == "GET" and path.startswith("/client/blockchain/multisig/"):
            funding_id = path.removeprefix("/client/blockchain/multisig/")
            return await get_client_blockchain_multisig.handle(self.node, funding_id)

        match method, path:
            case "GET", "/public-key":
                return await get_public_key.handle(self.node, body)
            case "GET", "/status":
                return await get_status.handle(self.node, body)
            case "GET", "/client/blockchain/status":
                return await get_client_blockchain_status.handle(self.node, body)
            case "GET", "/client/pending-fundings":
                return await get_client_pending_fundings.handle(self.node, body)
            case "POST", "/funding":
                return await post_funding.handle(self.node, body)
            case "POST", "/complete-funding":
                return await post_complete_funding.handle(self.node, body)
            case "POST", "/propose-update":
                return await post_propose_update.handle(self.node, body)
            case "POST", "/sign-pending-update":
                return await post_sign_pending_update.handle(self.node, body)
            case "POST", "/complete-update":
                return await post_complete_update.handle(self.node, body)
            case "POST", "/revoke-state":
                return await post_revoke_state.handle(self.node, body)
            case "POST", "/client/fund":
                return await post_client_fund.handle(self.node, body)
            case "POST", "/client/accept-funding":
                return await post_client_accept_funding.handle(self.node, body)
            case "POST", "/client/propose-update":
                return await post_client_propose_update.handle(self.node, body)
            case "POST", "/client/accept-update":
                return await post_client_accept_update.handle(self.node, body)
            case "POST", "/client/close-channel":
                return await post_client_close_channel.handle(self.node, body)
            case "POST", "/client/close-channel-invalid-signature":
                return await post_client_invalid_close_channel.handle(self.node, body)
            case "POST", "/client/claim-revoked-close":
                return await post_client_claim_revoked_close.handle(self.node, body)
            case "POST", "/client/finalize-close":
                return await post_client_finalize_close.handle(self.node, body)
            case _:
                return 404, b"Not Found\n", b"text/plain"

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
        if method == "OPTIONS":
            status, response_body, content_type = 204, b"", b"text/plain"
        else:
            status, response_body, content_type = await self.dispatch(method, path, body)

        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", content_type),
                    (b"access-control-allow-origin", b"*"),
                    (
                        b"access-control-allow-methods",
                        b"GET, POST, OPTIONS",
                    ),
                    (
                        b"access-control-allow-headers",
                        b"Content-Type",
                    ),
                ],
            }
        )
        await send({"type": "http.response.body", "body": response_body})
