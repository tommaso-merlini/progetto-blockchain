from . import commands


class ChannelCLI:
    def __init__(self, node):
        self.node = node

    async def handle_command(self, cmd_text: str) -> None:
        tokens = cmd_text.split()
        if not tokens:
            return

        command = tokens[0]
        if command == "fund":
            await commands.fund(self.node, tokens)
        elif command == "accept-funding":
            await commands.accept_funding(self.node, tokens)
        elif command == "propose-update":
            await commands.propose_update(self.node, tokens)
        elif command == "accept-update":
            await commands.accept_update(self.node, tokens)
        elif command == "status":
            await commands.status(self.node, tokens)
        else:
            print(f"[ERRORE] Comando sconosciuto: {command}")
            print(
                "Comandi disponibili: fund, accept-funding, propose-update, "
                "accept-update, status"
            )
