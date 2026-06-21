import hashlib
import json
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from domain_types import *

@dataclass
class PendingClose:
    channel_id: ChannelId
    transaction_id: TransactionId
    balances: Balances
    htlcs: List[HTLC]
    broadcaster: PublicKey
    revocation_hashes: RevocationMap
    at_height: int
    challenge_period: int

@dataclass
class MultiSigAddress:
    address: Address
    public_keys: Tuple[PublicKey, ...]
    threshold: int
    balance: Money
    initial_balances: Balances
    pending_close: Optional[PendingClose] = None
    settlement: Balances = field(default_factory=dict)

class BlockChain:
    def __init__(self, verbose=False):
        self.addresses: Dict[Address, MultiSigAddress] = {}
        self.height = 0
        self.verbose = verbose

    def log(self, msg: str):
        if self.verbose: print(f"[BLOCKCHAIN h:{self.height}] {msg}")

    @staticmethod
    def hash_fn(data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()

    @staticmethod
    def revocation_hash(cid: ChannelId, tx_id: TransactionId, owner: PublicKey, secret: RevocationSecret) -> str:
        payload = f"{cid}-{tx_id}-{owner}-{secret}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def multisig_payload(addr: Address, outputs: Balances, meta: Any) -> bytes:
        data = {"from": addr, "to": outputs, "meta": meta}
        return json.dumps(data, sort_keys=True).encode()

    def create_multi_sig_address(self, initial_balances: Balances, threshold: int) -> MultiSigAddress:
        pks = tuple(sorted(initial_balances.keys()))
        addr = hashlib.sha256("".join(pks).encode()).hexdigest()[:40]
        ms = MultiSigAddress(addr, pks, threshold, sum(initial_balances.values()), initial_balances)
        self.addresses[addr] = ms
        return ms

    def publish_commitment(self, addr: Address, outputs: Balances, htlcs: List[HTLC], sigs: SignatureMap, 
                           meta: Any, broadcaster: PublicKey, hashes: RevocationMap, challenge: int = 10):
        ms = self.addresses[addr]
        payload = self.multisig_payload(addr, outputs, meta)
        
        valid_sigs = 0
        for pk, s in sigs.items():
            if pk in ms.public_keys:
                pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pk))
                try:
                    pub.verify(bytes.fromhex(s), payload)
                    valid_sigs += 1
                except: continue
        
        if valid_sigs < ms.threshold: raise ValueError("Firme insufficienti")
        
        ms.pending_close = PendingClose(meta['channel_id'], meta['transaction_id'], outputs, 
                                        htlcs, broadcaster, hashes, self.height, challenge)
        ms.balance = 0
        self.log(f"TX:{meta['transaction_id']} pubblicata da {broadcaster[:8]}")

    def punish_commitment(self, addr: Address, punisher_pk: PublicKey, secret: RevocationSecret) -> Balances:
        ms = self.addresses[addr]
        pc = ms.pending_close
        if not pc: raise ValueError("No pending close")
        
        h = self.revocation_hash(pc.channel_id, pc.transaction_id, pc.broadcaster, secret)
        if h != pc.revocation_hashes[pc.broadcaster]: raise ValueError("Segreto errato")
        
        total = sum(pc.balances.values()) + sum(h.amount for h in pc.htlcs)
        ms.settlement = {punisher_pk: total}
        ms.pending_close = None
        self.log(f"PUNIZIONE: Frode rilevata! {total} monete assegnate a {punisher_pk[:8]}")
        return ms.settlement

    def claim_htlc_success(self, addr: Address, htlc_id: int, secret: PaymentSecret) -> Money:
        pc = self.addresses[addr].pending_close
        for h in pc.htlcs:
            if h.id == htlc_id and self.hash_fn(secret) == h.payment_hash:
                h.resolved = True
                self.log(f"HTLC {htlc_id} riscosso con segreto.")
                return h.amount
        raise ValueError("Segreto HTLC errato")

    def claim_htlc_timeout(self, addr: Address, htlc_id: int) -> Money:
        pc = self.addresses[addr].pending_close
        for h in pc.htlcs:
            if h.id == htlc_id and self.height >= h.expiration_height:
                h.resolved = True
                self.log(f"HTLC {htlc_id} rimborsato per timeout.")
                return h.amount
        raise ValueError("Timeout HTLC non raggiunto")

    def mine(self, blocks: int = 1):
        self.height += blocks
        if self.verbose: self.log(f"Minati {blocks} blocchi")