def validate_channel_balances(
    own_amount: object, peer_amount: object, capacity: int
) -> tuple[int, int]:
    if type(own_amount) is not int or type(peer_amount) is not int:
        raise ValueError("I bilanci devono essere numeri interi JSON, non stringhe o float")
    if own_amount < 0 or peer_amount < 0:
        raise ValueError("I bilanci non possono essere negativi")
    if own_amount > capacity or peer_amount > capacity:
        raise ValueError("I bilanci non possono superare la capacità del canale")
    if own_amount + peer_amount != capacity:
        raise ValueError(
            f"I bilanci proposti violano la capacità del canale: "
            f"{own_amount} + {peer_amount} != {capacity}"
        )
    return own_amount, peer_amount
