from __future__ import annotations

import logging
from collections.abc import Sequence

from clickhouse_driver import Client

from trade_tracker.models import Trade

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
ORDER BY (transaction_hash, trade_datetime)
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
) ENGINE = ReplacingMergeTree()
ORDER BY (transaction_hash, trade_datetime)
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
    #client.execute(CREATE_TRADES_TABLE.format(database=database, table=table))
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
    rows = client.execute(
        f"""
        SELECT t.transaction_hash, t.trade_datetime, t.pair_name,
               t.amount_base, t.amount_quote, t.price, t.type,
               g.`group`, g.gain_base, g.gain_quote, g.pct_price_change
        FROM {database}.{trades_table} t
        INNER JOIN (
            SELECT transaction_hash, trade_datetime, `group`,
                   gain_base, gain_quote, pct_price_change
            FROM {database}.{groups_table}
            ORDER BY trade_datetime DESC
            LIMIT 1 BY `group`
        ) g
        ON t.transaction_hash = g.transaction_hash
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
    client.execute(f"INSERT INTO {database}.{table} VALUES", rows)
    client.disconnect()
    logging.info("Exported %d group rows to ClickHouse (%s.%s)", len(rows), database, table)
