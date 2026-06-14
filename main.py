from dataclasses import dataclass
import hashlib
import json


@dataclass
class MultiSigAddress:
    address: str
    public_keys: tuple[str, ...]
    threshold: int
    balance: int = 0


@dataclass
class Channel:
    channel_id: int
    funding_address: str
    participants: tuple[str, ...]
    capacity: int
    balances: dict[str, int]
    is_open: bool = True


class BlockChain:
    def __init__(self):
        self.addresses: dict[str, MultiSigAddress] = {}
        self.channels: dict[int, Channel] = {}
        self.next_channel_id = 0

    def create_multi_sig_address(
        self, public_keys: list[str], threshold: int
    ) -> MultiSigAddress:
        unique_public_keys = tuple(sorted(set(public_keys)))

        if not unique_public_keys:
            raise ValueError("servono almeno una public key")
        if threshold < 1:
            raise ValueError("la threshold deve essere almeno 1")
        if threshold > len(unique_public_keys):
            raise ValueError("la threshold non puo' superare il numero di public key")

        address = self.derive_address(unique_public_keys, threshold)
        multi_sig_address = MultiSigAddress(address, unique_public_keys, threshold)
        self.addresses[address] = multi_sig_address
        return multi_sig_address

    def deposit(self, address: str, amount: int):
        if amount <= 0:
            raise ValueError("l'importo deve essere positivo")

        multi_sig_address = self.get_address(address)
        multi_sig_address.balance += amount

    def spend(
        self,
        from_address: str,
        to_address: str,
        amount: int,
        signatures: list[str],
    ):
        if amount <= 0:
            raise ValueError("l'importo deve essere positivo")

        multi_sig_address = self.get_address(from_address)
        if amount > multi_sig_address.balance:
            raise ValueError("saldo insufficiente")
        if not self.has_enough_valid_signatures(multi_sig_address, signatures):
            raise ValueError("firme valide insufficienti")

        multi_sig_address.balance -= amount
        print(f"sent {amount} from {from_address} to {to_address}")

    def open_lightning_channel(self, contributions: dict[str, int]) -> Channel:
        if len(contributions) != 2:
            raise ValueError("un canale Lightning base ha esattamente due partecipanti")
        if any(amount <= 0 for amount in contributions.values()):
            raise ValueError("ogni contributo deve essere positivo")

        participants = tuple(sorted(contributions))
        capacity = sum(contributions.values())
        funding_wallet = self.create_multi_sig_address(list(participants), 2)
        self.deposit(funding_wallet.address, capacity)

        channel = Channel(
            channel_id=self.next_channel_id,
            funding_address=funding_wallet.address,
            participants=participants,
            capacity=capacity,
            balances={
                participant: contributions[participant] for participant in participants
            },
        )
        self.channels[channel.channel_id] = channel
        self.next_channel_id += 1
        return channel

    def pay_in_channel(self, channel_id: int, sender: str, recipient: str, amount: int):
        channel = self.get_open_channel(channel_id)

        if sender not in channel.balances or recipient not in channel.balances:
            raise ValueError("sender e recipient devono essere nel canale")
        if amount <= 0:
            raise ValueError("l'importo deve essere positivo")
        if channel.balances[sender] < amount:
            raise ValueError("saldo del sender insufficiente nel canale")

        channel.balances[sender] -= amount
        channel.balances[recipient] += amount

    def close_channel(self, channel_id: int, signatures: list[str]) -> dict[str, int]:
        channel = self.get_open_channel(channel_id)
        funding_wallet = self.get_address(channel.funding_address)

        if not self.has_enough_valid_signatures(funding_wallet, signatures):
            raise ValueError("servono entrambe le firme per chiudere il canale")

        if sum(channel.balances.values()) != channel.capacity:
            raise ValueError("stato del canale incoerente")

        funding_wallet.balance = 0
        channel.is_open = False
        return dict(channel.balances)

    def derive_address(self, public_keys: tuple[str, ...], threshold: int) -> str:
        payload = json.dumps(
            {"public_keys": public_keys, "threshold": threshold},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:40]

    def get_address(self, address: str) -> MultiSigAddress:
        if address not in self.addresses:
            raise ValueError("address sconosciuto")
        return self.addresses[address]

    def has_enough_valid_signatures(
        self, multi_sig_address: MultiSigAddress, signatures: list[str]
    ) -> bool:
        valid_signers = set(signatures).intersection(multi_sig_address.public_keys)
        return len(valid_signers) >= multi_sig_address.threshold

    def get_open_channel(self, channel_id: int) -> Channel:
        if channel_id not in self.channels:
            raise ValueError("canale sconosciuto")

        channel = self.channels[channel_id]
        if not channel.is_open:
            raise ValueError("canale gia' chiuso")
        return channel

    def __str__(self):
        return str(self.addresses)


def main():
    bc = BlockChain()

    channel = bc.open_lightning_channel({"alice": 10, "bob": 5})
    print(channel)

    bc.pay_in_channel(channel.channel_id, "alice", "bob", 3)
    print(channel)

    final_balances = bc.close_channel(channel.channel_id, ["alice", "bob"])
    print(final_balances)


if __name__ == "__main__":
    main()
