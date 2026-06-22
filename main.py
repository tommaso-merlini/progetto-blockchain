import json
import re
import sys
from dataclasses import dataclass
from threading import Thread
from urllib.request import Request, urlopen

import uvicorn

from funding_transaction import (
    Contribution,
    FundingTransaction,
    create_funding_transaction,
)


@dataclass
class Channel:
    transactions: list[FundingTransaction]


channels: dict[str, Channel] = {}


async def app(scope, receive, send):
    body = b""
    while (message := await receive())["type"] == "http.request":
        body += message.get("body", b"")
        if not message.get("more_body"):
            break

    if scope["method"] == "POST" and scope["path"] == "/funding":
        try:
            data = json.loads(body)
            print(data)
            contributions = [Contribution(**item) for item in data["contributions"]]
            if len(contributions) != 2:
                raise ValueError
            tx = create_funding_transaction(*contributions)
            if data != json.loads(tx.serialize()):
                raise ValueError
            channels[tx.id] = Channel([tx])
            status, body = 200, tx.id.encode()
        except KeyError, TypeError, ValueError, json.JSONDecodeError:
            status, body = 400, b"Invalid funding transaction\n"
        content_type = b"text/plain; charset=utf-8"
    elif scope["method"] != "POST" or scope["path"] != "/command":
        status, body, content_type = 404, b"Not Found\n", b"text/plain;charset=UTF-8"
    else:
        text = body.decode(errors="replace")
        print(f"\n{text}")
        print("> ", end="", flush=True)
        status, content_type = 200, b"text/plain; charset=utf-8"

    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", content_type)],
        }
    )
    await send({"type": "http.response.body", "body": body})


def read_command(c: str):
    try:
        command, own_key, own_amount, peer_key, peer_amount, peer_url = c.split()
        if command != "fund":
            raise ValueError
        tx = create_funding_transaction(
            Contribution(own_key, int(own_amount)),
            Contribution(peer_key, int(peer_amount)),
        )
        request = Request(
            peer_url.rstrip("/") + "/funding", data=tx.serialize(), method="POST"
        )
        with urlopen(request, timeout=3) as response:
            if response.read().decode() != tx.id:
                raise ValueError("peer returned a different transaction ID")
        channels[tx.id] = Channel([tx])
        print(tx)
        print(tx.id)
    except (ValueError, OSError) as error:
        print(
            error
            or "Usage: fund <own_key> <own_amount> <peer_key> <peer_amount> <peer_url>"
        )


def main() -> None:
    argument = sys.argv[1] if len(sys.argv) > 1 else ""
    if (
        not re.fullmatch(r"[0-9]+", argument)
        or not 1 <= (port := int(argument)) <= 65_535
    ):
        raise SystemExit("Usage: python main.py <port>")

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="0.0.0.0",
            port=port,
            log_level="critical",
            access_log=False,
            lifespan="off",
        )
    )
    thread = Thread(target=server.run)
    thread.start()
    print(f"Listening on http://0.0.0.0:{port}")

    try:
        while True:
            try:
                read_command(input("> "))
            except EOFError:
                thread.join()
    except KeyboardInterrupt:
        print()
        server.should_exit = True
        thread.join()


if __name__ == "__main__":
    main()
