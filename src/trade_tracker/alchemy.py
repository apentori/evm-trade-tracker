from __future__ import annotations

import logging

import requests


class AlchemyClient:
    def __init__(self, rpc_url: str) -> None:
        self._rpc_url = rpc_url

    def get_blocks_for_address(self, wallet_address: str, from_block: int, to_block: int, direction: str) -> list[int]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "alchemy_getAssetTransfers",
            "params": [
                {
                    "fromBlock": hex(from_block),
                    "toBlock": hex(to_block),
                    direction: wallet_address,
                    "excludeZeroValue": True,
                    "withMetadata": True,
                    "category": ["erc20"],
                }
            ],
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(self._rpc_url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        transfers = response.json()["result"]["transfers"]
        blocks = sorted({int(transfer["blockNum"], 16) for transfer in transfers})
        logging.info("Found %d unique blocks for %s", len(blocks), direction)
        return blocks
