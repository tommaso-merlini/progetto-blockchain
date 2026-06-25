from http_api.routes import trigger_accept_funding


async def accept_funding(node, tokens: list[str]) -> None:
    if len(tokens) != 3:
        print("Uso: accept-funding <funding_id> <proposer_url>")
        return
    try:
        await trigger_accept_funding.run(node, tokens[1], tokens[2])
        print(f"\n[OK] Funding accettata e canale aperto: {tokens[1]}")
    except Exception as e:
        print(f"[ERRORE] Accettazione funding fallita: {e}")
