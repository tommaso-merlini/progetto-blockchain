import sys
import re
import asyncio
import uvicorn

from lightningnetwork import LightningNode
from http_api import HttpInterface
from cli import ChannelCLI

# Componenti core condivisi da CLI e server HTTP.
node = LightningNode()
interface = HttpInterface(node)


async def app(scope, receive, send):
    """Entrypoint ASGI a livello di modulo chiamato da Uvicorn."""
    await interface(scope, receive, send)


class SafeServer(uvicorn.Server):
    """Sottoclasse di Uvicorn che disabilita i gestori dei segnali per evitare eccezioni."""

    def install_signal_handlers(self) -> None:
        pass


async def main_async() -> None:
    if len(sys.argv) < 2 or not re.fullmatch(r"[0-9]+", sys.argv[1]):
        raise SystemExit("Uso: python src/main.py <port>")

    port = int(sys.argv[1])
    cli = ChannelCLI(node)

    # Usa l'app già in memoria: così CLI e server HTTP condividono lo stesso nodo.
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=port,
        log_level="critical",
        access_log=False,
        lifespan="off",
    )
    # Istanziazione del server sicuro privo di gestione segnali interna
    server = SafeServer(config)

    # Esecuzione del server ASGI nell'event loop corrente
    server_task = asyncio.create_task(server.serve())

    try:
        while not server.should_exit:
            try:
                cmd = await asyncio.to_thread(input, "> ")
                await cli.handle_command(cmd)
            except EOFError:
                # Mantiene attivo il server in ambienti di automazione non interattivi
                while not server.should_exit:
                    await asyncio.sleep(0.1)
                break
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        await server_task


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
