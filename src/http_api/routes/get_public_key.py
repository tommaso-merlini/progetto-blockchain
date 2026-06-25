from node import LightningNode


async def handle(node: LightningNode, body: bytes):
    return 200, node.public_key.encode(), b"text/plain; charset=utf-8"
