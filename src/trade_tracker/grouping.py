from __future__ import annotations

import logging
from typing import Any

from trade_tracker.exporters.clickhouse import (
    export_trades_group,
    fetch_last_group_trades,
    get_next_group_number,
)
from trade_tracker.models import Trade


def amounts_match(a: float, b: float) -> bool:
    return abs(a - b) < 1e-8 or abs(a - b) / max(abs(a), abs(b), 1.0) < 1e-4


def _price_favorable(incoming_type: str, incoming_price: float, last_price: float) -> bool:
    if incoming_type == "SELL":
        return incoming_price > last_price
    return incoming_price < last_price


def assign_groups(
    trades: list[Trade],
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    trades_table: str = "trades",
    groups_table: str = "trades_group",
) -> None:
    if not trades:
        return

    trades_sorted = sorted(trades, key=lambda t: t.trade_datetime)

    existing = fetch_last_group_trades(host, port, user, password, database, trades_table, groups_table)

    groups_by_pair: dict[str, list[dict[str, Any]]] = {}
    for g in existing:
        groups_by_pair.setdefault(g["pair_name"], []).append(g)

    pending_updates: list[dict[str, Any]] = []

    for pair_name, pair_trades in _group_by_pair(trades_sorted):
        pair_groups = groups_by_pair.get(pair_name, [])
        pair_groups.sort(key=lambda g: g["group"])

        next_num = get_next_group_number(host, port, user, password, database, groups_table, pair_name)

        for trade in pair_trades:
            matched = False
            for g in reversed(pair_groups):
                last_type = g["type"]
                last_amount_base = g["amount_base"]
                last_amount_quote = g["amount_quote"]
                last_price = g["price"]

                if trade.type == last_type:
                    continue

                base_ok = amounts_match(trade.amount_base, last_amount_base)
                quote_ok = amounts_match(trade.amount_quote, last_amount_quote)

                if not base_ok and not quote_ok:
                    continue

                if not _price_favorable(trade.type, trade.price, last_price):
                    continue

                group_name = g["group"]

                pending_updates.append(
                    {
                        "transaction_hash": g["transaction_hash"],
                        "trade_datetime": g["trade_datetime"],
                        "pair_name": pair_name,
                        "group": group_name,
                        "gain_base": g["gain_base"],
                        "gain_quote": g["gain_quote"],
                        "pct_price_change": g["pct_price_change"],
                        "status": "close",
                    }
                )

                gain_base = 0.0
                gain_quote = 0.0
                if base_ok:
                    if trade.type == "SELL":
                        gain_quote = trade.amount_quote - last_amount_quote
                    else:
                        gain_quote = last_amount_quote - trade.amount_quote
                else:
                    if trade.type == "BUY":
                        gain_base = trade.amount_base - last_amount_base
                    else:
                        gain_base = last_amount_base - trade.amount_base

                if trade.type == "SELL":
                    pct = (trade.price - last_price) / last_price
                else:
                    pct = (last_price - trade.price) / last_price

                row: dict[str, Any] = {
                    "transaction_hash": trade.transaction_hash,
                    "trade_datetime": trade.trade_datetime,
                    "pair_name": pair_name,
                    "group": group_name,
                    "gain_base": gain_base,
                    "gain_quote": gain_quote,
                    "pct_price_change": pct,
                    "status": "open",
                }
                pending_updates.append(row)

                g["transaction_hash"] = trade.transaction_hash
                g["trade_datetime"] = trade.trade_datetime
                g["amount_base"] = trade.amount_base
                g["amount_quote"] = trade.amount_quote
                g["price"] = trade.price
                g["type"] = trade.type
                g["gain_base"] = gain_base
                g["gain_quote"] = gain_quote
                g["pct_price_change"] = pct

                matched = True
                break

            if not matched:
                group_name = f"{pair_name}_{next_num}"
                next_num += 1
                row = {
                    "transaction_hash": trade.transaction_hash,
                    "trade_datetime": trade.trade_datetime,
                    "pair_name": pair_name,
                    "group": group_name,
                    "gain_base": 0.0,
                    "gain_quote": 0.0,
                    "pct_price_change": 0.0,
                    "status": "open",
                }
                pending_updates.append(row)

                pair_groups.append(
                    {
                        "transaction_hash": trade.transaction_hash,
                        "trade_datetime": trade.trade_datetime,
                        "amount_base": trade.amount_base,
                        "amount_quote": trade.amount_quote,
                        "price": trade.price,
                        "type": trade.type,
                        "group": group_name,
                        "pair_name": pair_name,
                        "gain_base": 0.0,
                        "gain_quote": 0.0,
                        "pct_price_change": 0.0,
                    }
                )

    export_trades_group(pending_updates, host, port, user, password, database, groups_table)

    logging.info("Assigned %d trades to groups", len(trades))


def _group_by_pair(trades: list[Trade]) -> list[tuple[str, list[Trade]]]:
    by_pair: dict[str, list[Trade]] = {}
    for t in trades:
        by_pair.setdefault(t.pair_name, []).append(t)
    return sorted(by_pair.items())
