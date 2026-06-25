async def status(node, _tokens: list[str]) -> None:
    if not node.channels:
        print("\nNessun canale attivo.")
    for channel_id, channel in node.channels.items():
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
                print(f"    Accetta con: accept-update {channel_id} <proposer_url>")
