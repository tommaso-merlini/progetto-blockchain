import sys
import re
import asyncio
import uvicorn

from node import LightningNode
from http_interface import HttpInterface

# Componenti core a livello di modulo per consentire il caricamento tramite stringa ("main:app")
node = LightningNode()
interface = HttpInterface(node)

async def app(scope, receive, send):
    """Entrypoint ASGI a livello di modulo chiamato da Uvicorn."""
    await interface(scope, receive, send)


class SafeServer(uvicorn.Server):
    """Sottoclasse di Uvicorn che disabilita i gestori dei segnali per evitare eccezioni."""
    def install_signal_handlers(self) -> None:
        pass


class ChannelCLI:
    def __init__(self, node: LightningNode, interface: HttpInterface):
        self.node = node
        self.interface = interface

    async def handle_command(self, cmd_text: str):
        """Gestisce i comandi CLI in modo nativamente asincrono."""
        tokens = cmd_text.split()
        if not tokens: 
            return
        command = tokens[0]
        
        if command == "fund":
            try:
                funding_id = await self.interface.trigger_fund_logic(tokens[1], tokens[2], tokens[3])
                print(f"\n[OK] Canale aperto con ID: {funding_id}")
            except Exception as e: 
                print(f"[ERRORE] Apertura canale fallita: {e}")
                
        elif command == "update":
            try:
                await self.interface.trigger_update_logic(tokens[1], tokens[2], tokens[3], tokens[4])
                print(f"\n[OK] Canale aggiornato.")
            except Exception as e: 
                print(f"[ERRORE] Aggiornamento del canale fallito: {e}")
                
        elif command == "status":
            if not self.node.channels:
                print("\nNessun canale attivo.")
            for channel_id, channel in self.node.channels.items():
                current_commitment = channel.commitments[channel.current_index]
                print(f"\nCanale ID: {channel_id}")
                print(f"  Stato Indice Corrente: {channel.current_index}")
                print(f"  Bilancio Locale: {current_commitment.own_amount}")
                print(f"  Bilancio Remoto: {current_commitment.peer_amount}")


async def main_async() -> None:
    if len(sys.argv) < 2 or not re.fullmatch(r"[0-9]+", sys.argv[1]):
        raise SystemExit("Uso: python main.py <port>")
        
    port = int(sys.argv[1])
    cli = ChannelCLI(node, interface)
    
    # Parametri puliti e compatibili con qualsiasi versione di Uvicorn
    config = uvicorn.Config(
        "main:app",
        host="0.0.0.0", 
        port=port, 
        log_level="critical", 
        access_log=False, 
        lifespan="off"
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