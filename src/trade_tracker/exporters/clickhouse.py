from __future__ import annotations

import logging
from collections.abc import Sequence

from clickhouse_driver import Client

from trade_tracker.models import Trade

CREATE_TRADES_TABLE = """
CREATE TABLE IF NOT EXISTS {database}.{table} (
    transaction_hash String,
    trade_timestamp   UInt32,
    block_number      UInt32,
    amount_eth        Float64,
    amount_usdc       Float64,
    eth_sender        String,
    eth_receiver      String,
    token             String,
    token_address     String,
    token_sender      String,
    token_receiver    String,
    price             Float64,
    type              String
) ENGINE = ReplacingMergeTree()
ORDER BY (transaction_hash, trade_timestamp)
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
    client.execute(CREATE_TRADES_TABLE.format(database=database, table=table))
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
