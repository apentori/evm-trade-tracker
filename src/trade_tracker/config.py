from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    alchemy_url: str = field(default_factory=lambda: os.getenv("ALCHEMY_URL", "https://opt-mainnet.g.alchemy.com/v2"))
    alchemy_api_key: str = field(default_factory=lambda: os.getenv("ALCHEMY_API_KEY", ""))

    clickhouse_host: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_HOST", "localhost"))
    clickhouse_port: int = field(default_factory=lambda: int(os.getenv("CLICKHOUSE_PORT", "9000")))
    clickhouse_user: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_USER", "default"))
    clickhouse_password: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_PASSWORD", ""))
    clickhouse_database: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_DATABASE", "default"))
    clickhouse_table: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_TABLE", "trades"))

    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


USDC_ADDRESS = "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85".lower()
USDC_OLD_ADDRESS = "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1".lower()
WETH_ADDRESS = "0x4200000000000000000000000000000000000006".lower()
WETH_OLD_ADDRESS = "0x4200000000000000000000000000000000000042".lower()

TRACKED_TOKENS = [USDC_ADDRESS, USDC_OLD_ADDRESS, WETH_ADDRESS]

ERC20_NAME_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    }
]

ERC20_DECIMALS_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    }
]

EVENT_TOPIC_TYPE: dict[str, str] = {
    "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f": "SWAP",
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": "TRANSFER",
    "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65": "WITHDRAWAL",
}

SWAP_ABI_TYPES = ["int128", "int128", "uint160", "uint128", "int24", "uint24"]
SWAP_ABI_NAMES = ["amount0", "amount1", "sqrtPriceX96", "liquidity", "tick", "fee"]

NULL_ADDRESS = "0x0000000000000000000000000000000000000000"
