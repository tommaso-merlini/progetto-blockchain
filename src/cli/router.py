from . import commands


class ChannelCLI:
    def __init__(self, node, interface):
        self.node = node
        self.interface = interface

    async def handle_command(self, cmd_text: str) -> None:
        tokens = cmd_text.split()
        if not tokens:
            return

        command = tokens[0]
        if command == "fund":
            await commands.fund(self.node, self.interface, tokens)
        elif command == "propose-update":
            await commands.propose_update(self.node, self.interface, tokens)
        elif command == "accept-update":
            await commands.accept_update(self.node, self.interface, tokens)
        elif command == "status":
            await commands.status(self.node, self.interface, tokens)
        else:
            print(f"[ERRORE] Comando sconosciuto: {command}")
            print(
                "Comandi disponibili: fund, propose-update, accept-update, status"
            )
