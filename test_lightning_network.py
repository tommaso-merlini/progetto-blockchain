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
        self.funding_wallet = self.blockchain.create_multi_sig_address(
            {self.alice.public_key: 10, self.bob.public_key: 5}, 2
        )
        self.channel = self.lightning_network.open_channel(self.funding_wallet.address)

    def create_commitment(self):
        secrets = self.create_revocation_secrets()
        return self.lightning_network.create_commitment(
            self.channel.channel_id,
            {
                self.alice.public_key: 8,
                self.bob.public_key: 7,
            },
            secrets,
        )

    def create_revocation_secrets(self):
        return {
            self.alice.public_key: self.lightning_network.generate_revocation_secret(),
            self.bob.public_key: self.lightning_network.generate_revocation_secret(),
        }

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
        transaction = self.create_commitment()

        with self.assertRaisesRegex(ValueError, "firmata correttamente"):
            self.lightning_network.close_channel(
                self.channel.channel_id,
                transaction.transaction_id,
            )

    def test_signature_must_match_declared_public_key(self):
        transaction = self.create_commitment()
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
        transaction = self.create_commitment()
        self.sign_with_both_participants(transaction)
        transaction.balances[self.alice.public_key] -= 1
        transaction.balances[self.bob.public_key] += 1

        with self.assertRaisesRegex(ValueError, "firmata correttamente"):
            self.lightning_network.close_channel(
                self.channel.channel_id,
                transaction.transaction_id,
            )

    def test_valid_signed_commitment_closes_channel(self):
        transaction = self.create_commitment()
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
        self.assertEqual(funding_wallet.settlement_balances, transaction.balances)

    def test_open_channel_does_not_create_initial_commitment(self):
        self.assertEqual(len(self.channel.commitments), 0)

    def test_open_channel_uses_funding_wallet_initial_balances(self):
        self.assertEqual(
            self.channel.participants,
            tuple(sorted([self.alice.public_key, self.bob.public_key])),
        )
        self.assertEqual(self.channel.capacity, 15)
        self.assertEqual(self.funding_wallet.balance, 15)

    def test_open_channel_requires_two_of_two_funding_wallet(self):
        funding_wallet = self.blockchain.create_multi_sig_address(
            {self.alice.public_key: 10, self.bob.public_key: 5}, 1
        )

        with self.assertRaisesRegex(ValueError, "2-of-2"):
            self.lightning_network.open_channel(funding_wallet.address)

    def test_create_commitment_can_create_initial_commitment(self):
        secrets = self.create_revocation_secrets()
        initial_commitment = self.lightning_network.create_commitment(
            self.channel.channel_id,
            {
                self.alice.public_key: 10,
                self.bob.public_key: 5,
            },
            secrets,
        )

        self.assertEqual(initial_commitment.transaction_id, 0)
        self.assertEqual(
            initial_commitment.balances,
            {
                self.alice.public_key: 10,
                self.bob.public_key: 5,
            },
        )
        self.assertEqual(set(initial_commitment.revocation_hashes), set(secrets))

    def test_commitment_balances_must_match_channel_capacity(self):
        with self.assertRaisesRegex(ValueError, "stato del canale incoerente"):
            self.lightning_network.create_commitment(
                self.channel.channel_id,
                {
                    self.alice.public_key: 8,
                    self.bob.public_key: 8,
                },
                self.create_revocation_secrets(),
            )

    def test_revealed_secret_punishes_old_commitment_on_chain(self):
        tx0_secrets = self.create_revocation_secrets()
        tx0 = self.lightning_network.create_commitment(
            self.channel.channel_id,
            {
                self.alice.public_key: 10,
                self.bob.public_key: 5,
            },
            tx0_secrets,
        )
        self.sign_with_both_participants(tx0)

        tx1 = self.lightning_network.create_commitment(
            self.channel.channel_id,
            {
                self.alice.public_key: 8,
                self.bob.public_key: 7,
            },
            self.create_revocation_secrets(),
        )
        self.sign_with_both_participants(tx1)

        self.lightning_network.reveal_revocation_secret(
            self.channel.channel_id,
            tx0.transaction_id,
            self.bob.public_key,
            tx0_secrets[self.bob.public_key],
        )

        self.lightning_network.publish_commitment(
            self.channel.channel_id,
            tx0.transaction_id,
            broadcaster=self.bob.public_key,
            challenge_period=2,
        )

        bob_old_secret = self.lightning_network.get_revealed_revocation_secret(
            self.channel.channel_id,
            tx0.transaction_id,
            self.bob.public_key,
        )
        settlement = self.blockchain.punish_commitment(
            self.channel.funding_address,
            punished_party=self.bob.public_key,
            beneficiary=self.alice.public_key,
            secret=bob_old_secret,
        )

        self.assertEqual(settlement, {self.alice.public_key: 15})
        funding_wallet = self.blockchain.get_address(self.channel.funding_address)
        self.assertIsNone(funding_wallet.pending_close)
        self.assertEqual(funding_wallet.settlement_balances, settlement)

    def test_latest_commitment_cannot_be_punished_without_secret(self):
        transaction = self.create_commitment()
        self.sign_with_both_participants(transaction)

        self.lightning_network.publish_commitment(
            self.channel.channel_id,
            transaction.transaction_id,
            broadcaster=self.bob.public_key,
            challenge_period=1,
        )

        with self.assertRaisesRegex(ValueError, "revocation secret non valido"):
            self.blockchain.punish_commitment(
                self.channel.funding_address,
                punished_party=self.bob.public_key,
                beneficiary=self.alice.public_key,
                secret="not-the-secret",
            )

    def test_pending_commitment_finalizes_after_challenge_period(self):
        transaction = self.create_commitment()
        self.sign_with_both_participants(transaction)

        self.lightning_network.publish_commitment(
            self.channel.channel_id,
            transaction.transaction_id,
            broadcaster=self.alice.public_key,
            challenge_period=2,
        )

        with self.assertRaisesRegex(ValueError, "challenge period"):
            self.blockchain.finalize_commitment(self.channel.funding_address)

        self.blockchain.mine_blocks(2)
        settlement = self.blockchain.finalize_commitment(self.channel.funding_address)

        self.assertEqual(settlement, transaction.balances)


if __name__ == "__main__":
    unittest.main()
