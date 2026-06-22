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
        self.alice.open_local_channel(self.channel, self.bob.public_key)
        self.bob.open_local_channel(self.channel, self.alice.public_key)

    def create_commitment(self):
        transaction_id = self.alice.get_local_channel(
            self.channel.channel_id
        ).next_transaction_id
        return self.lightning_network.create_commitment(
            self.channel.channel_id,
            transaction_id,
            {
                self.alice.public_key: 8,
                self.bob.public_key: 7,
            },
            self.create_revocation_hashes(transaction_id),
        )

    def create_revocation_hashes(self, transaction_id):
        return {
            actor.public_key: actor.create_channel_revocation_hash(
                self.channel.channel_id,
                transaction_id,
            )
            for actor in (self.alice, self.bob)
        }

    def update_channel(self, proposer, receiver, balances):
        transaction_id = proposer.get_local_channel(
            self.channel.channel_id
        ).next_transaction_id
        transaction = proposer.propose_commitment(
            self.lightning_network,
            self.channel.channel_id,
            balances,
            self.create_revocation_hashes(transaction_id),
        )
        receiver.receive_commitment_proposal(
            self.lightning_network,
            transaction,
            proposer.public_key,
        )
        proposer.receive_signed_commitment(
            self.lightning_network,
            transaction,
            receiver.public_key,
        )
        return transaction

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
                transaction,
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
                transaction,
            )

    def test_signature_covers_commitment_payload(self):
        transaction = self.create_commitment()
        self.sign_with_both_participants(transaction)
        transaction.balances[self.alice.public_key] -= 1
        transaction.balances[self.bob.public_key] += 1

        with self.assertRaisesRegex(ValueError, "firmata correttamente"):
            self.lightning_network.close_channel(
                transaction,
            )

    def test_valid_signed_commitment_closes_channel(self):
        transaction = self.create_commitment()
        self.sign_with_both_participants(transaction)

        with contextlib.redirect_stdout(io.StringIO()):
            final_balances = self.lightning_network.close_channel(
                transaction,
            )

        self.assertEqual(final_balances, transaction.balances)
        self.assertFalse(self.channel.is_open)
        funding_wallet = self.blockchain.get_address(self.channel.funding_address)
        self.assertEqual(funding_wallet.balance, 0)
        self.assertEqual(funding_wallet.settlement_balances, transaction.balances)

    def test_open_channel_does_not_create_initial_commitment(self):
        self.assertIsNone(
            self.alice.get_local_channel(self.channel.channel_id).current_commitment
        )
        self.assertIsNone(
            self.bob.get_local_channel(self.channel.channel_id).current_commitment
        )

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
        transaction_id = self.alice.get_local_channel(
            self.channel.channel_id
        ).next_transaction_id
        initial_commitment = self.lightning_network.create_commitment(
            self.channel.channel_id,
            transaction_id,
            {
                self.alice.public_key: 10,
                self.bob.public_key: 5,
            },
            self.create_revocation_hashes(transaction_id),
        )

        self.assertEqual(initial_commitment.transaction_id, 0)
        self.assertEqual(
            initial_commitment.balances,
            {
                self.alice.public_key: 10,
                self.bob.public_key: 5,
            },
        )
        self.assertEqual(
            set(initial_commitment.revocation_hashes),
            {self.alice.public_key, self.bob.public_key},
        )

    def test_commitment_balances_must_match_channel_capacity(self):
        with self.assertRaisesRegex(ValueError, "stato del canale incoerente"):
            transaction_id = self.alice.get_local_channel(
                self.channel.channel_id
            ).next_transaction_id
            self.lightning_network.create_commitment(
                self.channel.channel_id,
                transaction_id,
                {
                    self.alice.public_key: 8,
                    self.bob.public_key: 8,
                },
                self.create_revocation_hashes(transaction_id),
            )

    def test_revealed_secret_punishes_old_commitment_on_chain(self):
        tx0 = self.update_channel(
            self.alice,
            self.bob,
            {
                self.alice.public_key: 10,
                self.bob.public_key: 5,
            },
        )

        tx1 = self.update_channel(
            self.alice,
            self.bob,
            {
                self.alice.public_key: 8,
                self.bob.public_key: 7,
            },
        )

        bob_tx0_secret = self.bob.reveal_previous_secret(
            self.channel.channel_id,
            tx0.transaction_id,
        )
        self.alice.receive_revocation_secret(
            tx0,
            self.bob.public_key,
            bob_tx0_secret,
        )

        self.lightning_network.publish_commitment(
            tx0,
            broadcaster=self.bob.public_key,
            challenge_period=2,
        )

        bob_old_secret = self.alice.get_counterparty_revocation_secret(
            self.channel.channel_id,
            tx0.transaction_id,
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

    def test_secret_cannot_be_revealed_before_local_next_commitment_is_valid(self):
        tx0 = self.update_channel(
            self.alice,
            self.bob,
            {
                self.alice.public_key: 10,
                self.bob.public_key: 5,
            },
        )

        with self.assertRaisesRegex(ValueError, "commitment successiva"):
            self.alice.reveal_previous_secret(
                self.channel.channel_id,
                tx0.transaction_id,
            )

        transaction_id = self.alice.get_local_channel(
            self.channel.channel_id
        ).next_transaction_id
        tx1 = self.alice.propose_commitment(
            self.lightning_network,
            self.channel.channel_id,
            {
                self.alice.public_key: 8,
                self.bob.public_key: 7,
            },
            self.create_revocation_hashes(transaction_id),
        )
        self.bob.receive_commitment_proposal(
            self.lightning_network,
            tx1,
            self.alice.public_key,
        )

        with self.assertRaisesRegex(ValueError, "commitment successiva"):
            self.alice.reveal_previous_secret(
                self.channel.channel_id,
                tx0.transaction_id,
            )

        self.alice.receive_signed_commitment(
            self.lightning_network,
            tx1,
            self.bob.public_key,
        )

        secret = self.alice.reveal_previous_secret(
            self.channel.channel_id,
            tx0.transaction_id,
        )
        self.bob.receive_revocation_secret(tx0, self.alice.public_key, secret)
        self.assertEqual(
            self.bob.get_counterparty_revocation_secret(
                self.channel.channel_id,
                tx0.transaction_id,
            ),
            secret,
        )

    def test_latest_commitment_cannot_be_punished_without_secret(self):
        transaction = self.update_channel(
            self.alice,
            self.bob,
            {
                self.alice.public_key: 8,
                self.bob.public_key: 7,
            },
        )

        self.lightning_network.publish_commitment(
            transaction,
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
        transaction = self.update_channel(
            self.alice,
            self.bob,
            {
                self.alice.public_key: 8,
                self.bob.public_key: 7,
            },
        )

        self.lightning_network.publish_commitment(
            transaction,
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
