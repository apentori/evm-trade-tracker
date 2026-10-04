from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from click.testing import CliRunner

from trade_tracker.cli import main
from trade_tracker.config import Settings
from trade_tracker.models import Trade

WALLET = "0x503828976d22510aad0201ac7ec88293211d23da"


def _trade(tx_hash: str, pair: str = "ETH/USDC") -> Trade:
    return Trade(
        transaction_hash=tx_hash,
        trade_datetime=datetime.fromtimestamp(1000, tz=timezone.utc),
        block_number=100,
        pair_name=pair,
        base_token="0xbase",
        quote_token="0xquote",
        amount_base=1.0,
        amount_quote=2000.0,
        price=2000.0,
        type="BUY",
        sender=WALLET,
    )


def _invoke(known_keys: set | None = None):
    """Run the CLI in ClickHouse mode with the storage layer mocked out."""
    known_keys = known_keys if known_keys is not None else set()
    with (
        patch("trade_tracker.cli.load_settings", return_value=Settings(wallet_address=WALLET)),
        patch("trade_tracker.cli.Web3"),
        patch("trade_tracker.cli.AlchemyClient") as mock_alchemy,
        patch("trade_tracker.cli.scan_specific_blocks", return_value=[]),
        patch("trade_tracker.cli.create_trades", return_value=[_trade("0x1")]),
        patch("trade_tracker.cli.fetch_known_trade_keys", return_value=known_keys) as mock_known,
        patch("trade_tracker.cli.assign_groups") as mock_assign,
        patch("trade_tracker.cli.export_to_clickhouse") as mock_export,
    ):
        mock_alchemy.return_value.get_blocks_for_address.return_value = [100]
        result = CliRunner().invoke(
            main,
            ["-w", WALLET, "-k", "key", "--from-block", "100", "--to-block", "200"],
        )
    return result, mock_known, mock_assign, mock_export


def test_new_trades_are_grouped_and_exported():
    result, mock_known, mock_assign, mock_export = _invoke()
    assert result.exit_code == 0, result.output
    mock_assign.assert_called_once()
    mock_export.assert_called_once()
    exported = mock_export.call_args[0][0]
    assert [t.transaction_hash for t in exported] == ["0x1"]


def test_already_stored_trades_are_skipped():
    # Re-scanning an overlapping block range must not re-insert nor re-group
    # trades that are already stored.
    result, mock_known, mock_assign, mock_export = _invoke(known_keys={("0x1", "ETH/USDC")})
    assert result.exit_code == 0, result.output
    mock_assign.assert_not_called()
    mock_export.assert_not_called()


def test_to_json_does_not_touch_clickhouse():
    with (
        patch("trade_tracker.cli.load_settings", return_value=Settings(wallet_address=WALLET)),
        patch("trade_tracker.cli.Web3"),
        patch("trade_tracker.cli.AlchemyClient") as mock_alchemy,
        patch("trade_tracker.cli.scan_specific_blocks", return_value=[]),
        patch("trade_tracker.cli.create_trades", return_value=[_trade("0x1")]),
        patch("trade_tracker.cli.export_to_json") as mock_json,
        patch("trade_tracker.cli.fetch_known_trade_keys") as mock_known,
    ):
        mock_alchemy.return_value.get_blocks_for_address.return_value = [100]
        result = CliRunner().invoke(
            main,
            ["-w", WALLET, "-k", "key", "--to-block", "200", "--to-json"],
        )
    assert result.exit_code == 0, result.output
    mock_json.assert_called_once()
    mock_known.assert_not_called()
