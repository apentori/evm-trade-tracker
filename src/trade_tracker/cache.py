from __future__ import annotations

import logging

from web3 import Web3

from trade_tracker.config import ERC20_DECIMALS_ABI, ERC20_NAME_ABI


class TokenCache:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, str | int]] = {}

    def get_name(self, w3: Web3, token_address: str) -> str:
        key = token_address.lower()
        if key in self._cache and "name" in self._cache[key]:
            return str(self._cache[key]["name"])
        try:
            contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=ERC20_NAME_ABI)
            name = contract.functions.name().call()
            self._cache.setdefault(key, {})["name"] = name
            return name
        except Exception as e:
            logging.warning("Failed to fetch token name for %s: %s", token_address, e)
            return "Unknown"

    def get_decimals(self, w3: Web3, token_address: str) -> int:
        key = token_address.lower()
        if key in self._cache and "decimals" in self._cache[key]:
            return int(self._cache[key]["decimals"])
        try:
            contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=ERC20_DECIMALS_ABI)
            decimals = contract.functions.decimals().call()
            self._cache.setdefault(key, {})["decimals"] = decimals
            return decimals
        except Exception as e:
            logging.warning("Failed to fetch token decimals for %s: %s", token_address, e)
            return 18
