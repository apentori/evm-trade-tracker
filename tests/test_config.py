from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import trade_tracker.config as cfg
from trade_tracker.config import load_settings


def test_defaults():
    settings = load_settings()
    assert settings.alchemy_url == "https://opt-mainnet.g.alchemy.com/v2"
    assert settings.clickhouse_port == 9000
    assert settings.log_level == "INFO"
    assert len(settings.pairs) == 2
    assert settings.pairs[0].name == "ETH/USDC"
    assert settings.pairs[0].base_decimals == 18
    assert settings.null_address == cfg.NULL_ADDRESS
    assert "SWAP" in settings.event_topic_type.values()


def test_tracked_tokens_derived_from_pairs():
    settings = load_settings()
    tracked = settings.tracked_tokens
    assert len(tracked) == 3
    assert "0x0b2c639c533813f4aa9d7837caf62653d097ff85" in tracked
    assert "0x4200000000000000000000000000000000000006" in tracked
    assert "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1" in tracked


def test_pairs_via_yaml(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.dump(
            {
                "pairs": [
                    {
                        "name": "ETH/USD",
                        "base_token": "0xbase11111111111111111111111111111111111111",
                        "quote_token": "0xquote2222222222222222222222222222222222222",
                        "base_decimals": 18,
                        "quote_decimals": 8,
                    },
                ],
            }
        )
    )
    settings = load_settings(str(config))
    assert len(settings.pairs) == 1
    assert settings.pairs[0].name == "ETH/USD"
    assert settings.pairs[0].base_token == "0xbase11111111111111111111111111111111111111"
    assert settings.pairs[0].quote_decimals == 8


def test_multiple_pairs(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.dump(
            {
                "pairs": [
                    {"name": "A/B", "base_token": "0xaaa", "quote_token": "0xbbb"},
                    {"name": "C/D", "base_token": "0xccc", "quote_token": "0xddd"},
                ],
            }
        )
    )
    settings = load_settings(str(config))
    assert len(settings.pairs) == 2
    assert settings.pairs[1].name == "C/D"
    assert settings.tracked_tokens == ["0xaaa", "0xbbb", "0xccc", "0xddd"]


def test_yaml_partial(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.dump({"log_level": "WARNING"}))
    settings = load_settings(str(config))
    assert settings.log_level == "WARNING"
    assert len(settings.pairs) == 2


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


def test_apply_settings_updates_globals():
    settings = load_settings()
    cfg.apply_settings(settings)
    assert cfg.TRACKED_TOKENS == settings.tracked_tokens
    assert cfg.EVENT_TOPIC_TYPE == settings.event_topic_type
    assert cfg.NULL_ADDRESS == settings.null_address


def test_event_topic_type_via_yaml(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.dump({"events": {"topic_types": {"0xabc": "CUSTOM_EVENT"}}}))
    settings = load_settings(str(config))
    assert settings.event_topic_type == {"0xabc": "CUSTOM_EVENT"}
