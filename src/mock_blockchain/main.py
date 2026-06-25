import asyncio
import json
import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import uvicorn

from lightningnetwork import CommitmentTransaction
from mock_blockchain.state import MockBlockchain, funding_from_dict


DEFAULT_PORT = 9000
BLOCK_INTERVAL_SECONDS = float(os.environ.get("MOCK_BLOCK_INTERVAL_SECONDS", "30"))

blockchain = MockBlockchain()


class MockBlockchainApp:
    def __init__(self, state: MockBlockchain):
        self.state = state

    async def dispatch(self, method: str, path: str, body: bytes):
        try:
            if method == "GET" and path == "/block-number":
                return self.json_response({"block_number": self.state.block_number})

            if method == "GET" and path == "/status":
                return self.json_response(self.state.status())

            if method == "GET" and path.startswith("/multisig/"):
                funding_id = path.removeprefix("/multisig/")
                return self.json_response(self.state.multisig_status(funding_id))

            if method == "POST" and path == "/multisig":
                data = json.loads(body)
                funding = funding_from_dict(data["funding"])
                funding_id = self.state.add_multisig(funding)
                return self.json_response({"funding_id": funding_id})

            if method == "POST" and path == "/close-channel":
                data = json.loads(body)
                commitment = CommitmentTransaction.from_dict(data["commitment"])
                pending = self.state.publish_close(commitment)
                return self.json_response(
                    {
                        "funding_id": commitment.funding_id,
                        "published_at_block": pending.published_at_block,
                        "deadline_block": pending.deadline_block,
                    }
                )

            if method == "POST" and path == "/finalize-close":
                data = json.loads(body)
                return self.json_response(self.state.finalize_close(data["funding_id"]))

            if method == "POST" and path == "/claim-revoked-close":
                data = json.loads(body)
                return self.json_response(
                    self.state.claim_revoked_close(
                        data["funding_id"],
                        data["claimant"],
                        data["secret"],
                    )
                )

            return 404, b"Not Found\n", b"text/plain"
        except Exception as e:
            return 400, json.dumps({"error": str(e)}).encode(), b"application/json"

    @staticmethod
    def json_response(data: dict):
        return 200, json.dumps(data).encode(), b"application/json"

    async def __call__(self, scope, receive, send):
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
                    (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                    (b"access-control-allow-headers", b"Content-Type"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": response_body})


class SafeServer(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        pass


async def mine_blocks(server: uvicorn.Server) -> None:
    while not server.should_exit:
        await asyncio.sleep(BLOCK_INTERVAL_SECONDS)
        blockchain.mine_block()


async def main_async() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    config = uvicorn.Config(
        MockBlockchainApp(blockchain),
        host="0.0.0.0",
        port=port,
        log_level="critical",
        access_log=False,
        lifespan="off",
    )
    server = SafeServer(config)
    server_task = asyncio.create_task(server.serve())
    miner_task = asyncio.create_task(mine_blocks(server))
    try:
        await server_task
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        miner_task.cancel()
        try:
            await miner_task
        except asyncio.CancelledError:
            pass


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
