import re
import sys
from threading import Thread

import uvicorn


async def app(scope, receive, send):
    body = b""
    while (message := await receive())["type"] == "http.request":
        body += message.get("body", b"")
        if not message.get("more_body"):
            break

    if scope["method"] != "POST" or scope["path"] != "/command":
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
    print(c)


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
