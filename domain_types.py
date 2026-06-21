from typing import Dict, Tuple, Optional, Any, List
from dataclasses import dataclass, field

ActorId = str
Address = str
ChannelId = int
Money = int
PublicKey = str
RevocationHash = str
RevocationSecret = str
PaymentHash = str
PaymentSecret = str
Signature = str
TransactionId = int

Balances = Dict[PublicKey, Money]
SignatureMap = Dict[PublicKey, Signature]
RevocationMap = Dict[PublicKey, RevocationHash]

@dataclass
class HTLC:
    id: int
    amount: Money
    payment_hash: PaymentHash
    expiration_height: int
    sender: PublicKey
    receiver: PublicKey
    resolved: bool = False