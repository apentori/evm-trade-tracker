from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

# Maps an env var name to the Settings field it overrides.
ENV_FIELD_MAP: dict[str, str] = {
    "ALCHEMY_URL": "alchemy_url",
    "ALCHEMY_API_KEY": "alchemy_api_key",
    "WALLET_ADDRESS": "wallet_address",
    "CLICKHOUSE_HOST": "clickhouse_host",
    "CLICKHOUSE_PORT": "clickhouse_port",
    "CLICKHOUSE_USER": "clickhouse_user",
    "CLICKHOUSE_PASSWORD": "clickhouse_password",
    "CLICKHOUSE_DATABASE": "clickhouse_database",
    "CLICKHOUSE_TABLE": "clickhouse_table",
    "USDC_ADDRESS": "usdc_address",
    "USDC_OLD_ADDRESS": "usdc_old_address",
    "WETH_ADDRESS": "weth_address",
    "WETH_OLD_ADDRESS": "weth_old_address",
    "NULL_ADDRESS": "null_address",
    "LOG_LEVEL": "log_level",
}

# Maps a dotted YAML path to a Settings field.
YAML_FIELD_MAP: dict[tuple[str, ...], str] = {
    ("alchemy", "url"): "alchemy_url",
    ("alchemy", "api_key"): "alchemy_api_key",
    ("wallet_address",): "wallet_address",
    ("clickhouse", "host"): "clickhouse_host",
    ("clickhouse", "port"): "clickhouse_port",
    ("clickhouse", "user"): "clickhouse_user",
    ("clickhouse", "password"): "clickhouse_password",
    ("clickhouse", "database"): "clickhouse_database",
    ("clickhouse", "table"): "clickhouse_table",
    ("tokens", "usdc"): "usdc_address",
    ("tokens", "usdc_old"): "usdc_old_address",
    ("tokens", "weth"): "weth_address",
    ("tokens", "weth_old"): "weth_old_address",
    ("tokens", "tracked"): "tracked_tokens",
    ("events", "topic_types"): "event_topic_type",
    ("null_address",): "null_address",
    ("log_level",): "log_level",
}

# Type casters for fields that aren't str.
FIELD_TYPE: dict[str, Any] = {
    "clickhouse_port": int,
    "tracked_tokens": lambda v: tuple(v) if isinstance(v, list) else tuple(json.loads(v)),
    "event_topic_type": lambda v: v if isinstance(v, dict) else json.loads(v),
}


@dataclass(frozen=True)
class Settings:
    alchemy_url: str = "https://opt-mainnet.g.alchemy.com/v2"
    alchemy_api_key: str = ""
    wallet_address: str = ""
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 9000
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "default"
    clickhouse_table: str = "trades"
    usdc_address: str = "0x0b2c639c533813f4aa9d7837caf62653d097ff85"
    usdc_old_address: str = "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1"
    weth_address: str = "0x4200000000000000000000000000000000000006"
    weth_old_address: str = "0x4200000000000000000000000000000000000042"
    tracked_tokens: tuple[str, ...] = (
        "0x0b2c639c533813f4aa9d7837caf62653d097ff85",
        "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1",
        "0x4200000000000000000000000000000000000006",
    )
    null_address: str = "0x0000000000000000000000000000000000000000"
    event_topic_type: dict[str, str] = None  # type: ignore[assignment]
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.event_topic_type is None:
            object.__setattr__(
                self,
                "event_topic_type",
                {
                    "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f": "SWAP",
                    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": "TRANSFER",
                    "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65": "WITHDRAWAL",
                },
            )


def _search_paths() -> list[Path]:
    paths = [Path("trade-tracker.yaml")]
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        paths.insert(0, Path(xdg) / "trade-tracker" / "config.yaml")
    paths.append(Path.home() / ".config" / "trade-tracker" / "config.yaml")
    return paths


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _resolve_yaml(d: dict[str, Any], field_map: dict[tuple[str, ...], str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path, field in field_map.items():
        val: Any = d
        for key in path:
            if not isinstance(val, dict):
                val = None
                break
            val = val.get(key)
        if val is not None:
            caster = FIELD_TYPE.get(field)
            out[field] = caster(val) if caster else val
    return out


def load_settings(config_path: str | None = None) -> Settings:
    kwargs: dict[str, Any] = {}

    # 1. YAML file(s)
    if config_path:
        yaml_data = _read_yaml(Path(config_path))
        kwargs.update(_resolve_yaml(yaml_data, YAML_FIELD_MAP))
    else:
        for path in _search_paths():
            yaml_data = _read_yaml(path)
            kwargs.update(_resolve_yaml(yaml_data, YAML_FIELD_MAP))

    # 2. Environment variables override YAML
    for env_name, field in ENV_FIELD_MAP.items():
        val = os.environ.get(env_name)
        if val is not None:
            caster = FIELD_TYPE.get(field)
            kwargs[field] = caster(val) if caster else val

    # 3. Fill remaining gaps with Settings defaults
    final: dict[str, Any] = {}
    for fname in Settings.__dataclass_fields__:
        if fname in kwargs:
            final[fname] = kwargs[fname]
        else:
            final[fname] = getattr(Settings(), fname)

    return Settings(**final)


def apply_settings(settings: Settings) -> None:
    global USDC_ADDRESS, USDC_OLD_ADDRESS, WETH_ADDRESS, WETH_OLD_ADDRESS
    global TRACKED_TOKENS, EVENT_TOPIC_TYPE, NULL_ADDRESS
    USDC_ADDRESS = settings.usdc_address
    USDC_OLD_ADDRESS = settings.usdc_old_address
    WETH_ADDRESS = settings.weth_address
    WETH_OLD_ADDRESS = settings.weth_old_address
    TRACKED_TOKENS = list(settings.tracked_tokens)
    EVENT_TOPIC_TYPE = dict(settings.event_topic_type)
    NULL_ADDRESS = settings.null_address


# --- Module-level constants (overridable via apply_settings) ----------------

USDC_ADDRESS = "0x0b2c639c533813f4aa9d7837caf62653d097ff85"
USDC_OLD_ADDRESS = "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1"
WETH_ADDRESS = "0x4200000000000000000000000000000000000006"
WETH_OLD_ADDRESS = "0x4200000000000000000000000000000000000042"

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
