from __future__ import annotations

import argparse
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"Server is running\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def read_command() -> None:
    for line in sys.stdin:
        command = line.rstrip("\r\n")
        print(f"server echoed: {command}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an HTTP server and echo commands received on stdin."
    )
    parser.add_argument("port", type=int, help="TCP port on which to listen")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    return args


def main() -> None:
    args = parse_args()
    cli_thread = threading.Thread(target=read_command, daemon=True)
    cli_thread.start()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), RequestHandler)
    print(f"Listening on port {args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
