from http_api.routes import trigger_accept_update


async def accept_update(node, tokens: list[str]) -> None:
    if len(tokens) != 3:
        print("Uso: accept-update <funding_id> <proposer_url>")
        return
    funding_id = tokens[1]
    if funding_id not in node.channels:
        print(f"[ERRORE] Canale non trovato: {funding_id}")
        return
    try:
        await trigger_accept_update.run(node, funding_id, tokens[2])
        print("\n[OK] Proposta accettata e canale aggiornato.")
    except Exception as e:
        print(f"[ERRORE] Accettazione proposta fallita: {e}")
