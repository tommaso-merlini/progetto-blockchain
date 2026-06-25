from http_api.routes import trigger_propose_update
from lightningnetwork import validate_channel_balances


async def propose_update(node, tokens: list[str]) -> None:
    if len(tokens) != 5:
        print(
            "Uso: propose-update <funding_id> <new_own_amount> "
            "<new_peer_amount> <peer_url>"
        )
        return
    funding_id = tokens[1]
    if funding_id not in node.channels:
        print(f"[ERRORE] Canale non trovato: {funding_id}")
        return
    try:
        new_own = int(tokens[2])
        new_peer = int(tokens[3])
    except ValueError:
        print("[ERRORE] I nuovi bilanci devono essere numeri interi.")
        return
    capacity = node.channels[funding_id].funding.output.amount
    try:
        validate_channel_balances(new_own, new_peer, capacity)
    except ValueError as e:
        print(f"[ERRORE] Bilanci non validi: {e}")
        print(
            "Suggerimento: propose-update vuole il nuovo stato completo, "
            "non l'importo da pagare."
        )
        return
    try:
        await trigger_propose_update.run(
            node,
            funding_id,
            new_own,
            new_peer,
            tokens[4],
        )
        print("\n[OK] Proposta di aggiornamento inviata.")
        print("Il peer deve eseguire: accept-update <funding_id> <proposer_url>")
    except Exception as e:
        print(f"[ERRORE] Invio proposta fallito: {e}")
