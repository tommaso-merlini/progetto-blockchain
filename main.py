import json
import re
import sys
from dataclasses import dataclass
from threading import Thread
from urllib.request import Request, urlopen

import uvicorn
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from commitment_transaction import CommitmentTransaction, create_commitment
from funding_transaction import (
    Contribution,
    FundingTransaction,
    create_funding_transaction,
)


@dataclass
class Channel:
    funding: FundingTransaction
    commitment: CommitmentTransaction


channels: dict[str, Channel] = {}
private_key = Ed25519PrivateKey.generate()
public_key = private_key.public_key().public_bytes_raw().hex()


def parse_funding(data: dict) -> FundingTransaction:
    contributions = [Contribution(**item) for item in data["contributions"]]
    if len(contributions) != 2:
        raise ValueError
    transaction = create_funding_transaction(*contributions)
    if data != json.loads(transaction.serialize()):
        raise ValueError
    return transaction


async def app(scope, receive, send):
    body = b""
    while (message := await receive())["type"] == "http.request":
        body += message.get("body", b"")
        if not message.get("more_body"):
            break

    if scope["method"] == "GET" and scope["path"] == "/public-key":
        status, body = 200, public_key.encode()
        content_type = b"text/plain; charset=utf-8"
    elif scope["method"] == "POST" and scope["path"] == "/funding":
        try:
            data = json.loads(body)
            print(data)
            funding = parse_funding(data["funding"])
            peers = [
                item.public_key
                for item in funding.contributions
                if item.public_key != public_key
            ]
            if len(peers) != 1:
                raise ValueError

            own_commitment = create_commitment(funding, public_key)
            if not own_commitment.verify(peers[0], data["signature"]):
                raise ValueError
            own_commitment.signatures = {
                peers[0]: data["signature"],
                public_key: own_commitment.sign(private_key),
            }
            # TODO: make retries idempotent.
            channels[funding.id] = Channel(funding, own_commitment)

            peer_commitment = create_commitment(funding, peers[0])
            response = {
                "funding_id": funding.id,
                "signature": peer_commitment.sign(private_key),
            }
            status, body = 200, json.dumps(response).encode()
        except KeyError, TypeError, ValueError, json.JSONDecodeError:
            status, body = 400, b"Invalid funding transaction\n"
        content_type = b"application/json"
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
        command, own_amount, peer_amount, peer_url = c.split()
        if command != "fund":
            raise ValueError
        with urlopen(peer_url.rstrip("/") + "/public-key", timeout=3) as response:
            peer_key = response.read().decode()

        funding = create_funding_transaction(
            Contribution(public_key, int(own_amount)),
            Contribution(peer_key, int(peer_amount)),
        )
        peer_commitment = create_commitment(funding, peer_key)
        data = json.dumps(
            {
                "funding": json.loads(funding.serialize()),
                "signature": peer_commitment.sign(private_key),
            }
        ).encode()
        request = Request(peer_url.rstrip("/") + "/funding", data=data, method="POST")
        with urlopen(request, timeout=3) as response:
            answer = json.loads(response.read())
            if answer["funding_id"] != funding.id:
                raise ValueError("peer returned a different transaction ID")
        own_commitment = create_commitment(funding, public_key)
        if not own_commitment.verify(peer_key, answer["signature"]):
            raise ValueError("invalid peer signature")
        own_commitment.signatures = {
            public_key: own_commitment.sign(private_key),
            peer_key: answer["signature"],
        }
        channels[funding.id] = Channel(funding, own_commitment)
        print(own_commitment)
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as error:
        print(error or "Usage: fund <own_amount> <peer_amount> <peer_url>")


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
    print(f"Public key: {public_key}")

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
