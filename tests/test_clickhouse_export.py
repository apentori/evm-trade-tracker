from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from trade_tracker.exporters.clickhouse import export_trades_group


def _row(tx_hash: str, status: str) -> dict:
    return {
        "transaction_hash": tx_hash,
        "trade_datetime": datetime.fromtimestamp(1000, tz=timezone.utc),
        "pair_name": "ETH/USDC",
        "group": "ETH/USDC_1",
        "gain_base": 0.0,
        "gain_quote": 0.0,
        "pct_price_change": 0.0,
        "status": status,
    }


@patch("trade_tracker.exporters.clickhouse.Client")
def test_export_trades_group_assigns_strictly_increasing_versions(mock_client):
    rows = [
        _row("0xA1", "open"),  # written first when the group is created
        _row("0xA1", "close"),  # written later when a new trade closes the group
        _row("0xB2", "open"),
    ]
    export_trades_group(rows, "h", 9000, "u", "p", "db", "trades_group")

    sent_rows = mock_client.return_value.execute.call_args[0][1]
    versions = [r["version"] for r in sent_rows]
    assert versions == sorted(versions), "versions must be increasing in row order"
    assert len(set(versions)) == len(versions), "versions must be unique"
    # The "close" row for a trade must out-version its earlier "open" row so
    # ReplacingMergeTree(version) keeps it after the merge.
    assert versions[1] > versions[0]


@patch("trade_tracker.exporters.clickhouse.Client")
def test_export_trades_group_keeps_original_fields(mock_client):
    rows = [_row("0xA1", "open")]
    export_trades_group(rows, "h", 9000, "u", "p", "db", "trades_group")

    sent_rows = mock_client.return_value.execute.call_args[0][1]
    assert sent_rows[0]["status"] == "open"
    assert sent_rows[0]["transaction_hash"] == "0xA1"
    assert "version" in sent_rows[0]
    # The input rows are not mutated.
    assert "version" not in rows[0]
