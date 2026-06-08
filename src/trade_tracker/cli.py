from __future__ import annotations

import logging

import click
from web3 import Web3

from trade_tracker.alchemy import AlchemyClient
from trade_tracker.blockchain import scan_blocks_range, scan_specific_blocks
from trade_tracker.exporters.clickhouse import export_to_clickhouse, get_last_block_number
from trade_tracker.exporters.json_exporter import export_to_json
from trade_tracker.trades import create_trades

DEFAULT_URL = "https://opt-mainnet.g.alchemy.com/v2"


@click.command()
@click.option("-u", "--url", default=DEFAULT_URL, help="Alchemy URL")
@click.option("-w", "--wallet-address", required=True, help="Wallet address to scan")
@click.option("-k", "--api-key", required=True, help="API key")
@click.option(
    "--to-block",
    type=int,
    default=None,
    help="Latest block number to scan (default: current block)",
)
@click.option("--from-block", type=int, default=0, help="From block number to scan")
@click.option("-f", "--full", is_flag=True, default=False, help="Scan every block (slow)")
@click.option("--log-level", "-l", default="INFO", help="Log level")
@click.option("--to-json", is_flag=True, default=False, help="Export to trades.json instead of ClickHouse")
@click.option("--ch-host", default="localhost", help="ClickHouse host")
@click.option("--ch-port", type=int, default=9000, help="ClickHouse port")
@click.option("--ch-user", default="default", help="ClickHouse user")
@click.option("--ch-password", default="", help="ClickHouse password")
@click.option("--ch-database", default="default", help="ClickHouse database")
@click.option("--ch-table", default="trades", help="ClickHouse table name")
@click.option(
    "--follow",
    is_flag=True,
    default=False,
    help="Follow mode: auto-detect from-block from last stored trade (requires ClickHouse)",
)
def main(
    url: str,
    wallet_address: str,
    api_key: str,
    to_block: int | None,
    from_block: int,
    full: bool,
    log_level: str,
    to_json: bool,
    ch_host: str,
    ch_port: int,
    ch_user: str,
    ch_password: str,
    ch_database: str,
    ch_table: str,
    follow: bool,
) -> None:
    logging.basicConfig(level=log_level.upper())
    rpc_url = f"{url}/{api_key}"
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    if follow:
        if to_json:
            raise click.ClickException("--follow requires ClickHouse mode, not --to-json")
        last_block = get_last_block_number(ch_host, ch_port, ch_user, ch_password, ch_database, ch_table)
        from_block = (last_block or 0) + 1
        to_block = w3.eth.block_number
    else:
        if to_block is None:
            to_block = w3.eth.block_number

    logging.info("Scanning blocks %s to %s", hex(from_block), to_block)

    if full:
        transactions = scan_blocks_range(w3, wallet_address, from_block, to_block)
    else:
        alchemy = AlchemyClient(rpc_url)
        blocks = alchemy.get_blocks_for_address(
            wallet_address, from_block, to_block, "fromAddress"
        ) + alchemy.get_blocks_for_address(wallet_address, from_block, to_block, "toAddress")
        transactions = scan_specific_blocks(w3, wallet_address, sorted(set(blocks)))

    logging.info("Found %d transaction batches", len(transactions))
    trades = create_trades(w3, transactions, wallet_address)
    logging.info("Created %d trades", len(trades))

    if to_json:
        export_to_json(trades)
    else:
        export_to_clickhouse(trades, ch_host, ch_port, ch_user, ch_password, ch_database, ch_table)


if __name__ == "__main__":
    main()
