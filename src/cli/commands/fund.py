from http_api.routes import trigger_fund


async def fund(node, tokens: list[str]) -> None:
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
        funding_id = await trigger_fund.run(node, own_amount, peer_amount, tokens[3])
        print(f"\n[OK] Canale aperto con ID: {funding_id}")
    except Exception as e:
        print(f"[ERRORE] Apertura canale fallita: {e}")
