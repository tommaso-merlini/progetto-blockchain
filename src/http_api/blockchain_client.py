import json

from lightningnetwork import CommitmentTransaction, FundingTransaction

from .client import NetworkClient


MOCK_BLOCKCHAIN_URL = "http://localhost:9000"


class MockBlockchainClient:
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
