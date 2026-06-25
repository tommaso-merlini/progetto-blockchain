import json

from lightningnetwork import CommitmentTransaction, FundingTransaction

from .client import NetworkClient


MOCK_BLOCKCHAIN_URL = "http://localhost:9000"


class MockBlockchainClient:
    @staticmethod
    async def get_status() -> dict:
        return await NetworkClient.get(f"{MOCK_BLOCKCHAIN_URL}/status")

    @staticmethod
    async def get_multisig_status(funding_id: str) -> dict:
        return await NetworkClient.get(f"{MOCK_BLOCKCHAIN_URL}/multisig/{funding_id}")

    @staticmethod
    async def register_multisig(funding: FundingTransaction) -> dict:
        return await NetworkClient.post(
            f"{MOCK_BLOCKCHAIN_URL}/multisig",
            {"funding": json.loads(funding.serialize().decode())},
        )

    @staticmethod
    async def publish_close(commitment: CommitmentTransaction) -> dict:
        return await NetworkClient.post(
            f"{MOCK_BLOCKCHAIN_URL}/close-channel",
            {"commitment": commitment.to_dict()},
        )

    @staticmethod
    async def finalize_close(funding_id: str) -> dict:
        return await NetworkClient.post(
            f"{MOCK_BLOCKCHAIN_URL}/finalize-close",
            {"funding_id": funding_id},
        )

    @staticmethod
    async def claim_revoked_close(funding_id: str, claimant: str, secret: str) -> dict:
        return await NetworkClient.post(
            f"{MOCK_BLOCKCHAIN_URL}/claim-revoked-close",
            {
                "funding_id": funding_id,
                "claimant": claimant,
                "secret": secret,
            },
        )
