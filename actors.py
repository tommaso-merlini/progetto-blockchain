import secrets
from dataclasses import dataclass, field
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from blockchain import BlockChain
from domain_types import *

@dataclass
class Commitment:
    tx_id: TransactionId
    balances: Balances
    htlcs: List[HTLC]
    revocation_hashes: RevocationMap
    signatures: SignatureMap = field(default_factory=dict)

@dataclass
class LocalState:
    cid: ChannelId
    addr: Address
    counterparty: PublicKey
    capacity: Money
    commitments: List[Commitment] = field(default_factory=list)
    my_secrets: Dict[TransactionId, RevocationSecret] = field(default_factory=dict)
    counterparty_secrets: Dict[TransactionId, RevocationSecret] = field(default_factory=dict)
    pending_comm: Optional[Commitment] = None

class Actor:
    def __init__(self, actor_id: ActorId, verbose=False):
        self.id = actor_id
        self._key = Ed25519PrivateKey.generate()
        self.pub_key = self._key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ).hex()
        self.channels: Dict[ChannelId, LocalState] = {}
        self.payment_secrets: Dict[PaymentHash, PaymentSecret] = {}
        self.known_secrets: Dict[PaymentHash, PaymentSecret] = {} # Segreti scoperti durante il routing
        self.verbose = verbose

    def log(self, msg: str):
        if self.verbose: print(f"[ACTOR {self.id}] {msg}")

    def sign(self, data: bytes) -> Signature:
        return self._key.sign(data).hex()

    def init_channel(self, cid: ChannelId, addr: Address, cp: PublicKey, cap: Money):
        self.channels[cid] = LocalState(cid, addr, cp, cap)

    def sync_state_with(self, peer: 'Actor', cid: ChannelId, balances: Balances, htlcs: List[HTLC] = None):
        """Protocollo P2P in 8 step per aggiornare lo stato del canale."""
        htlcs = htlcs or []
        tx_id = len(self.channels[cid].commitments)
        
        # 1-2. Scambio Hash di revoca
        h_self = self._prepare_proposal(cid)
        h_peer = peer._prepare_proposal(cid)
        hashes = {self.pub_key: h_self, peer.pub_key: h_peer}

        # 3-4. Scambio Firme
        sig_self = self._sign_commitment(cid, tx_id, balances, htlcs, hashes)
        sig_peer = peer._sign_commitment(cid, tx_id, balances, htlcs, hashes)

        # 5. Finalizzazione locale
        self._finalize(cid, sig_peer)
        peer._finalize(cid, sig_self)

        # 6-8. Scambio Segreti di Revoca per invalidare lo stato precedente
        if tx_id > 0:
            prev = tx_id - 1
            sec_self = self.get_revocation_secret(cid, prev)
            sec_peer = peer.get_revocation_secret(cid, prev)
            self.store_revocation_secret(cid, prev, sec_peer)
            peer.store_revocation_secret(cid, prev, sec_self)

    def _prepare_proposal(self, cid: ChannelId) -> RevocationHash:
        state = self.channels[cid]
        tx_id = len(state.commitments)
        secret = secrets.token_hex(32)
        state.my_secrets[tx_id] = secret
        return BlockChain.revocation_hash(cid, tx_id, self.pub_key, secret)

    def _sign_commitment(self, cid: ChannelId, tx_id: TransactionId, balances: Balances, 
                        htlcs: List[HTLC], hashes: RevocationMap) -> Signature:
        state = self.channels[cid]
        payload = BlockChain.multisig_payload(state.addr, balances, {"channel_id": cid, "transaction_id": tx_id})
        state.pending_comm = Commitment(tx_id, balances, htlcs, hashes)
        return self.sign(payload)

    def _finalize(self, cid: ChannelId, counterparty_sig: Signature):
        state = self.channels[cid]
        state.pending_comm.signatures[state.counterparty] = counterparty_sig
        state.pending_comm.signatures[self.pub_key] = self.sign(
            BlockChain.multisig_payload(state.addr, state.pending_comm.balances, 
                                       {"channel_id": cid, "transaction_id": state.pending_comm.tx_id})
        )
        state.commitments.append(state.pending_comm)
        state.pending_comm = None

    def get_revocation_secret(self, cid: ChannelId, tx_id: TransactionId) -> RevocationSecret:
        return self.channels[cid].my_secrets[tx_id]

    def store_revocation_secret(self, cid: ChannelId, tx_id: TransactionId, secret: RevocationSecret):
        self.channels[cid].counterparty_secrets[tx_id] = secret

    def create_payment_hash(self) -> PaymentHash:
        secret = secrets.token_hex(32)
        p_hash = BlockChain.hash_fn(secret)
        self.payment_secrets[p_hash] = secret
        self.known_secrets[p_hash] = secret
        return p_hash