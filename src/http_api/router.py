from lightningnetwork import LightningNode

from .routes import (
    get_public_key,
    get_status,
    post_client_accept_update,
    post_client_fund,
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
        match method, path:
            case "GET", "/public-key":
                return await get_public_key.handle(self.node, body)
            case "GET", "/status":
                return await get_status.handle(self.node, body)
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
            case "POST", "/client/propose-update":
                return await post_client_propose_update.handle(self.node, body)
            case "POST", "/client/accept-update":
                return await post_client_accept_update.handle(self.node, body)
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
        status, response_body, content_type = await self.dispatch(method, path, body)

        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", content_type)],
            }
        )
        await send({"type": "http.response.body", "body": response_body})
