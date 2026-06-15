import contextlib
import io
import unittest

from actors import Actors
from blockchain import BlockChain
from lightning_network import LightningNetwork


class LightningSignatureTests(unittest.TestCase):
    def setUp(self):
        self.blockchain = BlockChain()
        self.lightning_network = LightningNetwork(self.blockchain)
        self.actors = Actors()
        self.alice = self.actors.create_actor("alice", "Alice")
        self.bob = self.actors.create_actor("bob", "Bob")
        self.channel = self.lightning_network.open_channel(
            {self.alice.public_key: 10, self.bob.public_key: 5}
        )

    def create_payment(self):
        return self.lightning_network.pay_in_channel(
            self.channel.channel_id,
            self.alice.public_key,
            self.bob.public_key,
            2,
        )

    def sign_with_both_participants(self, transaction):
        transaction.add_signature(
            self.alice.public_key,
            self.alice.sign(transaction.payload()),
        )
        transaction.add_signature(
            self.bob.public_key,
            self.bob.sign(transaction.payload()),
        )

    def test_close_requires_commitment_signatures(self):
        transaction = self.create_payment()

        with self.assertRaisesRegex(ValueError, "firmata correttamente"):
            self.lightning_network.close_channel(
                self.channel.channel_id,
                transaction.transaction_id,
            )

    def test_signature_must_match_declared_public_key(self):
        transaction = self.create_payment()
        transaction.add_signature(
            self.alice.public_key,
            self.alice.sign(transaction.payload()),
        )
        transaction.add_signature(
            self.bob.public_key,
            self.alice.sign(transaction.payload()),
        )

        with self.assertRaisesRegex(ValueError, "firmata correttamente"):
            self.lightning_network.close_channel(
                self.channel.channel_id,
                transaction.transaction_id,
            )

    def test_signature_covers_commitment_payload(self):
        transaction = self.create_payment()
        self.sign_with_both_participants(transaction)
        transaction.balances[self.alice.public_key] -= 1
        transaction.balances[self.bob.public_key] += 1

        with self.assertRaisesRegex(ValueError, "firmata correttamente"):
            self.lightning_network.close_channel(
                self.channel.channel_id,
                transaction.transaction_id,
            )

    def test_valid_signed_commitment_closes_channel(self):
        transaction = self.create_payment()
        self.sign_with_both_participants(transaction)

        with contextlib.redirect_stdout(io.StringIO()):
            final_balances = self.lightning_network.close_channel(
                self.channel.channel_id,
                transaction.transaction_id,
            )

        self.assertEqual(final_balances, transaction.balances)
        self.assertFalse(self.channel.is_open)
        funding_wallet = self.blockchain.get_address(self.channel.funding_address)
        self.assertEqual(funding_wallet.balance, 0)


if __name__ == "__main__":
    unittest.main()
