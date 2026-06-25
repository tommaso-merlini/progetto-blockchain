import sys
import re
import asyncio
import uvicorn

from node import LightningNode
from http_interface import HttpInterface

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
            if len(tokens) != 4:
                print("Uso: fund <own_amount> <peer_amount> <peer_url>")
                return
            try:
                own_amount = int(tokens[1])
                peer_amount = int(tokens[2])
            except ValueError:
                print("[ERRORE] Gli importi di fund devono essere numeri interi.")
                return
            try:
                funding_id = await self.interface.trigger_fund_logic(
                    own_amount, peer_amount, tokens[3]
                )
                print(f"\n[OK] Canale aperto con ID: {funding_id}")
            except Exception as e:
                print(f"[ERRORE] Apertura canale fallita: {e}")

        elif command in ("update", "propose-update"):
            if len(tokens) != 5:
                print(
                    "Uso: update <funding_id> <new_own_amount> <new_peer_amount> <peer_url>"
                )
                return
            funding_id = tokens[1]
            if funding_id not in self.node.channels:
                print(f"[ERRORE] Canale non trovato: {funding_id}")
                return
            try:
                new_own = int(tokens[2])
                new_peer = int(tokens[3])
            except ValueError:
                print("[ERRORE] I nuovi bilanci devono essere numeri interi.")
                return
            capacity = self.node.channels[funding_id].funding.output.amount
            if new_own + new_peer != capacity:
                print(
                    f"[ERRORE] Bilanci non validi: {new_own} + {new_peer} = "
                    f"{new_own + new_peer}, ma la capacità del canale è {capacity}."
                )
                print(
                    "Suggerimento: update vuole il nuovo stato completo, non l'importo da pagare."
                )
                return
            try:
                await self.interface.trigger_propose_update_logic(
                    funding_id, new_own, new_peer, tokens[4]
                )
                print("\n[OK] Proposta di aggiornamento inviata.")
                print(
                    "Il peer deve eseguire: accept-update <funding_id> <proposer_url>"
                )
            except Exception as e:
                print(f"[ERRORE] Invio proposta fallito: {e}")

        elif command == "accept-update":
            if len(tokens) != 3:
                print("Uso: accept-update <funding_id> <proposer_url>")
                return
            funding_id = tokens[1]
            if funding_id not in self.node.channels:
                print(f"[ERRORE] Canale non trovato: {funding_id}")
                return
            try:
                await self.interface.trigger_accept_update_logic(funding_id, tokens[2])
                print("\n[OK] Proposta accettata e canale aggiornato.")
            except Exception as e:
                print(f"[ERRORE] Accettazione proposta fallita: {e}")

        elif command == "status":
            if not self.node.channels:
                print("\nNessun canale attivo.")
            for channel_id, channel in self.node.channels.items():
                current_commitment = channel.commitments[channel.current_index]
                print(f"\nCanale ID: {channel_id}")
                print(f"  Stato Indice Corrente: {channel.current_index}")
                print(f"  Bilancio Locale: {current_commitment.own_amount}")
                print(f"  Bilancio Remoto: {current_commitment.peer_amount}")
                if channel.pending_update:
                    pending = channel.pending_update
                    if pending.get("role") == "proposer":
                        pending_own = pending["own_amount"]
                        pending_peer = pending["peer_amount"]
                        role = "inviata"
                    else:
                        pending_own = pending["peer_amount"]
                        pending_peer = pending["own_amount"]
                        role = "ricevuta"
                    print(f"  Proposta Pendente: {role}")
                    print(f"    Prossimo Indice: {pending.get('next_index')}")
                    print(f"    Nuovo Bilancio Locale: {pending_own}")
                    print(f"    Nuovo Bilancio Remoto: {pending_peer}")
                    if pending.get("role") != "proposer":
                        print(
                            f"    Accetta con: accept-update {channel_id} <proposer_url>"
                        )
        else:
            print(f"[ERRORE] Comando sconosciuto: {command}")
            print(
                "Comandi disponibili: fund, update, propose-update, accept-update, status"
            )


async def main_async() -> None:
    if len(sys.argv) < 2 or not re.fullmatch(r"[0-9]+", sys.argv[1]):
        raise SystemExit("Uso: python main.py <port>")

    port = int(sys.argv[1])
    cli = ChannelCLI(node, interface)

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
