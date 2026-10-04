from __future__ import annotations

import logging
import time
from collections.abc import Sequence

from clickhouse_driver import Client

from trade_tracker.models import Trade

# NOTE on table design:
# - ReplacingMergeTree only collapses rows with the same sorting key during
#   background merges, which happen at an unpredictable time. Reads therefore
#   need FINAL (see fetch_last_group_trades) to get deduplicated results.
# - The `version` column makes the collapse deterministic: the row with the
#   highest version survives, so a trade's "close" row (written later) always
#   replaces its earlier "open" row.
# - `pair_name` is part of the sorting key: a single transaction can produce
#   trades for several pairs (same hash + block timestamp), which must not be
#   treated as duplicates of each other.

CREATE_TRADES_TABLE = """
CREATE OR REPLACE TABLE {database}.{table} (
    transaction_hash  String,
    trade_datetime    DateTime,
    block_number      UInt32,
    pair_name         String,
    base_token        String,
    quote_token       String,
    amount_base       Float64,
    amount_quote      Float64,
    price             Float64,
    type              String,
    sender            String,
) ENGINE = ReplacingMergeTree()
ORDER BY (transaction_hash, pair_name, trade_datetime)
"""

CREATE_TRADES_GROUP_TABLE = """
CREATE OR REPLACE TABLE {database}.{table} (
    transaction_hash  String,
    trade_datetime    DateTime,
    pair_name         String,
    `group`           String,
    gain_base         Float64,
    gain_quote        Float64,
    pct_price_change  Float64,
    status            String,
    version           UInt64 DEFAULT 0,
) ENGINE = ReplacingMergeTree(version)
ORDER BY (transaction_hash, pair_name, trade_datetime)
"""


def export_to_clickhouse(
    trades: Sequence[Trade],
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table: str,
) -> None:
    dict_data = [t.to_dict() for t in trades]
    if not dict_data:
        logging.info("No trades to export")
        return

    client = Client(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    # client.execute(CREATE_TRADES_TABLE.format(database=database, table=table))
    client.execute(f"INSERT INTO {table} VALUES", dict_data)
    client.disconnect()
    logging.info("Exported %d trades to ClickHouse (%s.%s)", len(dict_data), database, table)


def get_last_block_number(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table: str,
) -> int:
    client = Client(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    rows = client.execute(f"SELECT MAX(block_number) FROM {database}.{table}")
    client.disconnect()
    return rows[0][0] if rows and rows[0][0] else 0


def fetch_last_group_trades(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    trades_table: str,
    groups_table: str,
) -> list[dict]:
    client = Client(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    # FINAL collapses not-yet-merged duplicates (e.g. a trade's "open" row
    # superseded by its "close" row) so the query always sees the latest
    # state of every trade. The join includes pair_name because one
    # transaction can produce trades for several pairs.
    rows = client.execute(
        f"""
        SELECT t.transaction_hash, t.trade_datetime, t.pair_name,
               t.amount_base, t.amount_quote, t.price, t.type,
               g.`group`, g.gain_base, g.gain_quote, g.pct_price_change
        FROM {database}.{trades_table} t
        INNER JOIN (
            SELECT transaction_hash, pair_name, trade_datetime, `group`,
                   gain_base, gain_quote, pct_price_change
            FROM {database}.{groups_table} FINAL
            ORDER BY trade_datetime DESC, transaction_hash DESC
            LIMIT 1 BY `group`
        ) g
        ON t.transaction_hash = g.transaction_hash
        AND t.pair_name = g.pair_name
        AND t.trade_datetime = g.trade_datetime
        """
    )
    client.disconnect()
    return [
        {
            "transaction_hash": r[0],
            "trade_datetime": r[1],
            "pair_name": r[2],
            "amount_base": r[3],
            "amount_quote": r[4],
            "price": r[5],
            "type": r[6],
            "group": r[7],
            "gain_base": r[8],
            "gain_quote": r[9],
            "pct_price_change": r[10],
        }
        for r in rows
    ]


def get_next_group_number(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table: str,
    pair_name: str,
) -> int:
    client = Client(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    prefix = f"{pair_name}_"
    rows = client.execute(
        f"""
        SELECT toUInt64OrZero(SUBSTRING(`group`, %(start)s))
        FROM {database}.{table}
        WHERE pair_name = %(pair_name)s
        """,
        {"start": len(prefix) + 1, "pair_name": pair_name},
    )
    client.disconnect()
    numbers = [r[0] for r in rows if r[0] and r[0] > 0]
    return max(numbers, default=0) + 1


def fetch_known_trade_keys(
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    groups_table: str = "trades_group",
) -> set[tuple[str, str]]:
    """Return (transaction_hash, pair_name) keys of trades already stored.

    Used to make processing idempotent: re-scanning blocks that were already
    processed (overlapping --from-block/--to-block ranges or webhook retries)
    must not re-insert trades nor re-group them.
    """
    client = Client(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    rows = client.execute(f"SELECT DISTINCT transaction_hash, pair_name FROM {database}.{groups_table}")
    client.disconnect()
    return {(r[0], r[1]) for r in rows}


def export_trades_group(
    rows: list[dict],
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    table: str,
) -> None:
    if not rows:
        logging.info("No group rows to export")
        return
    client = Client(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    # Assign a strictly increasing version to every row so that
    # ReplacingMergeTree(version) deterministically keeps the latest state of
    # a trade, e.g. a "close" row always replaces the older "open" row with
    # the same sorting key. The base differs between runs, and the row index
    # orders rows within a run (a trade's "close" row is always appended
    # after its "open" row).
    version_base = time.time_ns() // 1000
    data = [{**row, "version": version_base + i} for i, row in enumerate(rows)]
    client.execute(f"INSERT INTO {database}.{table} VALUES", data)
    client.disconnect()
    logging.info("Exported %d group rows to ClickHouse (%s.%s)", len(data), database, table)
