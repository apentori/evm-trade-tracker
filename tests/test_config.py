from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import trade_tracker.config as cfg
from trade_tracker.config import apply_settings, load_settings


def test_defaults():
    settings = load_settings()
    assert settings.alchemy_url == "https://opt-mainnet.g.alchemy.com/v2"
    assert settings.clickhouse_port == 9000
    assert settings.log_level == "INFO"
    assert settings.usdc_address == cfg.USDC_ADDRESS
    assert settings.null_address == cfg.NULL_ADDRESS
    assert "SWAP" in settings.event_topic_type.values()


def test_yaml_file(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.dump(
            {
                "alchemy": {"url": "https://custom.url", "api_key": "key-from-yaml"},
                "wallet_address": "0xabc",
                "clickhouse": {"host": "ch.example.com", "port": 8123},
                "log_level": "DEBUG",
            }
        )
    )
    settings = load_settings(str(config))
    assert settings.alchemy_url == "https://custom.url"
    assert settings.alchemy_api_key == "key-from-yaml"
    assert settings.wallet_address == "0xabc"
    assert settings.clickhouse_host == "ch.example.com"
    assert settings.clickhouse_port == 8123
    assert settings.log_level == "DEBUG"


def test_yaml_partial(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.dump({"log_level": "WARNING"}))
    settings = load_settings(str(config))
    assert settings.log_level == "WARNING"
    assert settings.alchemy_url == "https://opt-mainnet.g.alchemy.com/v2"
    assert settings.clickhouse_port == 9000


def test_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "from-env")
    monkeypatch.setenv("CLICKHOUSE_PORT", "8123")

    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.dump(
            {
                "alchemy": {"api_key": "from-yaml", "url": "https://yaml.url"},
                "clickhouse": {"port": 9000},
            }
        )
    )
    settings = load_settings(str(config))
    assert settings.alchemy_api_key == "from-env"
    assert settings.alchemy_url == "https://yaml.url"
    assert settings.clickhouse_port == 8123


def test_env_without_yaml(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ALCHEMY_API_KEY", "just-env")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    settings = load_settings()
    assert settings.alchemy_api_key == "just-env"
    assert settings.log_level == "ERROR"


def test_no_file_falls_back_to_defaults():
    settings = load_settings("/nonexistent/path/config.yaml")
    assert settings.alchemy_url == "https://opt-mainnet.g.alchemy.com/v2"


def test_empty_yaml(tmp_path: Path):
    config = tmp_path / "empty.yaml"
    config.write_text("")
    settings = load_settings(str(config))
    assert settings.clickhouse_user == "default"


def test_settings_frozen():
    settings = load_settings()
    with pytest.raises(AttributeError):
        settings.alchemy_url = "changed"  # type: ignore[misc]


def test_token_config_via_yaml(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.dump(
            {
                "tokens": {
                    "usdc": "0x1111111111111111111111111111111111111111",
                    "weth": "0x2222222222222222222222222222222222222222",
                    "tracked": [
                        "0x1111111111111111111111111111111111111111",
                        "0x2222222222222222222222222222222222222222",
                    ],
                },
                "null_address": "0xdead000000000000000000000000000000000000",
            }
        )
    )
    settings = load_settings(str(config))
    assert settings.usdc_address == "0x1111111111111111111111111111111111111111"
    assert settings.usdc_old_address == "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1"
    assert settings.weth_address == "0x2222222222222222222222222222222222222222"
    assert settings.weth_old_address == "0x4200000000000000000000000000000000000042"
    assert settings.null_address == "0xdead000000000000000000000000000000000000"
    assert len(settings.tracked_tokens) == 2


def test_event_topic_type_via_yaml(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.dump(
            {
                "events": {
                    "topic_types": {
                        "0xabc": "CUSTOM_EVENT",
                    }
                }
            }
        )
    )
    settings = load_settings(str(config))
    assert settings.event_topic_type == {"0xabc": "CUSTOM_EVENT"}


def test_token_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("WETH_ADDRESS", "0xdead00000000000000000000000000000000dead")
    settings = load_settings()
    assert settings.weth_address == "0xdead00000000000000000000000000000000dead"
    assert settings.usdc_address == "0x0b2c639c533813f4aa9d7837caf62653d097ff85"


def test_apply_settings_updates_globals(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.dump(
            {
                "tokens": {
                    "usdc": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "tracked": ["0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"],
                },
                "null_address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "events": {"topic_types": {"0xaaa": "FOO", "0xbbb": "BAR"}},
            }
        )
    )
    settings = load_settings(str(config))
    apply_settings(settings)
    assert cfg.USDC_ADDRESS == "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    assert cfg.NULL_ADDRESS == "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    assert cfg.TRACKED_TOKENS == ["0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"]
    assert cfg.EVENT_TOPIC_TYPE == {"0xaaa": "FOO", "0xbbb": "BAR"}
