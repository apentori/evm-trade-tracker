from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from trade_tracker.grouping import _price_favorable, amounts_match, assign_groups
from trade_tracker.models import Trade


def _trade(
    hash: str,
    pair: str,
    amount_base: float,
    amount_quote: float,
    price: float,
    type_: str,
    ts: int = 1000,
) -> Trade:
    return Trade(
        transaction_hash=hash,
        trade_datetime=datetime.fromtimestamp(ts, tz=timezone.utc),
        block_number=1,
        pair_name=pair,
        base_token="0xbase",
        quote_token="0xquote",
        amount_base=amount_base,
        amount_quote=amount_quote,
        price=price,
        type=type_,
        sender="0xsender",
    )


class TestAmountsMatch:
    def test_exact_match(self):
        assert amounts_match(1.0, 1.0) is True

    def test_zero_values(self):
        assert amounts_match(0.0, 0.0) is True

    def test_fuzzy_tolerance(self):
        assert amounts_match(1.0, 1.000000001) is True

    def test_relative_tolerance(self):
        assert amounts_match(1000.0, 1000.1) is True

    def test_no_match(self):
        assert amounts_match(1.0, 2.0) is False

    def test_zero_and_small(self):
        assert amounts_match(0.0, 1e-9) is True


class TestPriceFavorable:
    def test_buy_then_sell_higher(self):
        assert _price_favorable("SELL", 2000.0, 1900.0) is True

    def test_buy_then_sell_lower(self):
        assert _price_favorable("SELL", 1800.0, 1900.0) is False

    def test_sell_then_buy_lower(self):
        assert _price_favorable("BUY", 1800.0, 2000.0) is True

    def test_sell_then_buy_higher(self):
        assert _price_favorable("BUY", 2100.0, 2000.0) is False


class TestAssignGroups:
    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_new_group_created(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = []
        mock_next_num.return_value = 1

        trades = [_trade("0x1", "ETH/USDC", 1.0, 2000.0, 2000.0, "BUY", ts=1000)]
        assign_groups(trades, "h", 9000, "u", "p", "db")

        mock_export.assert_called_once()
        rows = mock_export.call_args[0][0]
        assert len(rows) == 1
        assert rows[0]["group"] == "ETH/USDC_1"
        assert rows[0]["status"] == "open"
        assert rows[0]["gain_base"] == 0.0
        assert rows[0]["gain_quote"] == 0.0
        assert rows[0]["pct_price_change"] == 0.0

    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_match_by_base_amount(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = [
            {
                "transaction_hash": "0x1",
                "trade_datetime": datetime.fromtimestamp(1000, tz=timezone.utc),
                "pair_name": "ETH/USDC",
                "amount_base": 1.0,
                "amount_quote": 1900.0,
                "price": 1900.0,
                "type": "BUY",
                "group": "ETH/USDC_1",
                "gain_base": 0.0,
                "gain_quote": 0.0,
                "pct_price_change": 0.0,
            }
        ]
        mock_next_num.return_value = 2

        trades = [_trade("0x2", "ETH/USDC", 1.0, 2000.0, 2000.0, "SELL", ts=2000)]
        assign_groups(trades, "h", 9000, "u", "p", "db")

        rows = mock_export.call_args[0][0]
        assert len(rows) == 2

        close_row = rows[0]
        assert close_row["transaction_hash"] == "0x1"
        assert close_row["status"] == "close"

        open_row = rows[1]
        assert open_row["transaction_hash"] == "0x2"
        assert open_row["group"] == "ETH/USDC_1"
        assert open_row["status"] == "open"
        assert open_row["gain_base"] == 0.0
        assert open_row["gain_quote"] == 100.0
        assert open_row["pct_price_change"] == pytest.approx(100.0 / 1900.0)

    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_match_by_quote_amount(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = [
            {
                "transaction_hash": "0x1",
                "trade_datetime": datetime.fromtimestamp(1000, tz=timezone.utc),
                "pair_name": "ETH/USDC",
                "amount_base": 0.1,
                "amount_quote": 200.0,
                "price": 2000.0,
                "type": "SELL",
                "group": "ETH/USDC_1",
                "gain_base": 0.0,
                "gain_quote": 0.0,
                "pct_price_change": 0.0,
            }
        ]
        mock_next_num.return_value = 2

        trades = [_trade("0x2", "ETH/USDC", 0.1526, 200.0, 1310.6, "BUY", ts=2000)]
        assign_groups(trades, "h", 9000, "u", "p", "db")

        rows = mock_export.call_args[0][0]
        assert len(rows) == 2

        open_row = rows[1]
        assert open_row["group"] == "ETH/USDC_1"
        assert open_row["status"] == "open"
        assert open_row["gain_quote"] == 0.0
        assert open_row["gain_base"] == pytest.approx(0.1526 - 0.1)
        assert open_row["pct_price_change"] == pytest.approx((2000.0 - 1310.6) / 2000.0)

    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_no_match_same_type(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = [
            {
                "transaction_hash": "0x1",
                "trade_datetime": datetime.fromtimestamp(1000, tz=timezone.utc),
                "pair_name": "ETH/USDC",
                "amount_base": 1.0,
                "amount_quote": 1900.0,
                "price": 1900.0,
                "type": "BUY",
                "group": "ETH/USDC_1",
                "gain_base": 0.0,
                "gain_quote": 0.0,
                "pct_price_change": 0.0,
            }
        ]
        mock_next_num.return_value = 2

        trades = [_trade("0x2", "ETH/USDC", 1.0, 1900.0, 1900.0, "BUY", ts=2000)]
        assign_groups(trades, "h", 9000, "u", "p", "db")

        rows = mock_export.call_args[0][0]
        assert len(rows) == 1
        assert rows[0]["group"] == "ETH/USDC_2"

    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_no_match_unfavorable_price(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = [
            {
                "transaction_hash": "0x1",
                "trade_datetime": datetime.fromtimestamp(1000, tz=timezone.utc),
                "pair_name": "ETH/USDC",
                "amount_base": 1.0,
                "amount_quote": 1900.0,
                "price": 1900.0,
                "type": "BUY",
                "group": "ETH/USDC_1",
                "gain_base": 0.0,
                "gain_quote": 0.0,
                "pct_price_change": 0.0,
            }
        ]
        mock_next_num.return_value = 2

        trades = [_trade("0x2", "ETH/USDC", 1.0, 1800.0, 1800.0, "SELL", ts=2000)]
        assign_groups(trades, "h", 9000, "u", "p", "db")

        rows = mock_export.call_args[0][0]
        assert len(rows) == 1
        assert rows[0]["group"] == "ETH/USDC_2"

    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_multiple_pairs(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = []
        mock_next_num.side_effect = [1, 1]

        trades = [
            _trade("0x1", "ETH/USDC", 1.0, 2000.0, 2000.0, "BUY", ts=1000),
            _trade("0x2", "OP/USDC", 100.0, 500.0, 5.0, "BUY", ts=1001),
        ]
        assign_groups(trades, "h", 9000, "u", "p", "db")

        rows = mock_export.call_args[0][0]
        assert len(rows) == 2
        assert rows[0]["group"] == "ETH/USDC_1"
        assert rows[1]["group"] == "OP/USDC_1"

    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_newest_group_wins(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = [
            {
                "transaction_hash": "0x1",
                "trade_datetime": datetime.fromtimestamp(1000, tz=timezone.utc),
                "pair_name": "ETH/USDC",
                "amount_base": 1.0,
                "amount_quote": 1900.0,
                "price": 1900.0,
                "type": "BUY",
                "group": "ETH/USDC_1",
                "gain_base": 0.0,
                "gain_quote": 0.0,
                "pct_price_change": 0.0,
            },
            {
                "transaction_hash": "0x2",
                "trade_datetime": datetime.fromtimestamp(1500, tz=timezone.utc),
                "pair_name": "ETH/USDC",
                "amount_base": 1.0,
                "amount_quote": 1900.0,
                "price": 1900.0,
                "type": "BUY",
                "group": "ETH/USDC_2",
                "gain_base": 0.0,
                "gain_quote": 0.0,
                "pct_price_change": 0.0,
            },
        ]
        mock_next_num.return_value = 3

        trades = [_trade("0x3", "ETH/USDC", 1.0, 2000.0, 2000.0, "SELL", ts=2000)]
        assign_groups(trades, "h", 9000, "u", "p", "db")

        rows = mock_export.call_args[0][0]
        assert len(rows) == 2
        close_row = rows[0]
        open_row = rows[1]
        assert close_row["transaction_hash"] == "0x2"
        assert open_row["group"] == "ETH/USDC_2"

    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_sequential_match_in_single_batch(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        mock_fetch.return_value = [
            {
                "transaction_hash": "0x1",
                "trade_datetime": datetime.fromtimestamp(1000, tz=timezone.utc),
                "pair_name": "ETH/USDC",
                "amount_base": 1.0,
                "amount_quote": 1900.0,
                "price": 1900.0,
                "type": "BUY",
                "group": "ETH/USDC_1",
                "gain_base": 0.0,
                "gain_quote": 0.0,
                "pct_price_change": 0.0,
            }
        ]
        mock_next_num.return_value = 2

        trades = [
            _trade("0x2", "ETH/USDC", 1.0, 2000.0, 2000.0, "SELL", ts=1500),
            _trade("0x3", "ETH/USDC", 1.0, 2100.0, 2100.0, "BUY", ts=2000),
        ]
        assign_groups(trades, "h", 9000, "u", "p", "db")

        rows = mock_export.call_args[0][0]
        assert len(rows) == 3

        group_names = {r["group"] for r in rows}
        assert group_names == {"ETH/USDC_1", "ETH/USDC_2"}
        close_rows = [r for r in rows if r["status"] == "close"]
        open_rows = [r for r in rows if r["status"] == "open"]
        assert len(close_rows) == 1
        assert len(open_rows) == 2
        assert close_rows[0]["transaction_hash"] == "0x1"
        open_tx_hashes = {r["transaction_hash"] for r in open_rows}
        assert open_tx_hashes == {"0x2", "0x3"}

    @patch("trade_tracker.grouping.fetch_last_group_trades")
    @patch("trade_tracker.grouping.get_next_group_number")
    @patch("trade_tracker.grouping.export_trades_group")
    def test_no_trades_does_nothing(
        self,
        mock_export: MagicMock,
        mock_next_num: MagicMock,
        mock_fetch: MagicMock,
    ):
        assign_groups([], "h", 9000, "u", "p", "db")
        mock_export.assert_not_called()
