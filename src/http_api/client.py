import asyncio
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def parse_http_error_body(body: bytes, fallback: str) -> str:
    text = body.decode(errors="replace").strip()
    if not text:
        return fallback
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(data, dict) and data.get("error"):
        return str(data["error"])
    return text


class NetworkClient:
    """Gestisce le richieste HTTP uscenti in modo non bloccante per l'event loop."""

    @staticmethod
    async def post(url: str, payload: dict) -> dict:
        def _sync_post():
            req = Request(
                url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(req, timeout=5) as response:
                    return json.loads(response.read().decode())
            except HTTPError as e:
                detail = parse_http_error_body(e.read(), e.reason)
                raise RuntimeError(
                    f"{url} ha risposto HTTP {e.code}: {detail}"
                ) from e
            except URLError as e:
                raise RuntimeError(f"Connessione fallita verso {url}: {e.reason}") from e
            except ValueError as e:
                raise RuntimeError(
                    f"URL non valido: {url}. Usa un URL completo, per esempio "
                    "http://127.0.0.1:1234"
                ) from e

        return await asyncio.to_thread(_sync_post)

    @staticmethod
    async def fetch_public_key(peer_url: str) -> str:
        def _sync_get():
            url = f"{peer_url.rstrip('/')}/public-key"
            try:
                with urlopen(url, timeout=3) as response:
                    return response.read().decode().strip()
            except HTTPError as e:
                detail = parse_http_error_body(e.read(), e.reason)
                raise RuntimeError(
                    f"{url} ha risposto HTTP {e.code}: {detail}"
                ) from e
            except URLError as e:
                raise RuntimeError(f"Connessione fallita verso {url}: {e.reason}") from e
            except ValueError as e:
                raise RuntimeError(
                    f"URL non valido: {url}. Usa un URL completo, per esempio "
                    "http://127.0.0.1:1234"
                ) from e

        return await asyncio.to_thread(_sync_get)
