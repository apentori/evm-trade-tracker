from __future__ import annotations

import logging

import click
from web3 import Web3

from trade_tracker.alchemy import AlchemyClient
from trade_tracker.blockchain import scan_blocks_range, scan_specific_blocks
from trade_tracker.config import apply_settings, load_settings
from trade_tracker.exporters.clickhouse import export_to_clickhouse, get_last_block_number
from trade_tracker.exporters.json_exporter import export_to_json
from trade_tracker.trades import create_trades


@click.command()
@click.option("--config", type=click.Path(exists=False), default=None, help="Path to YAML config file")
@click.option("-u", "--url", default=None, help="Alchemy URL")
@click.option("-w", "--wallet-address", default=None, help="Wallet address to scan")
@click.option("-k", "--api-key", default=None, help="API key")
@click.option("--to-block", type=int, default=None, help="Latest block number to scan (default: current block)")
@click.option("--from-block", type=int, default=None, help="From block number to scan")
@click.option("-f", "--full", is_flag=True, default=False, help="Scan every block (slow)")
@click.option("--log-level", "-l", default=None, help="Log level")
@click.option("--to-json", is_flag=True, default=False, help="Export to trades.json instead of ClickHouse")
@click.option("--ch-host", default=None, help="ClickHouse host")
@click.option("--ch-port", type=int, default=None, help="ClickHouse port")
@click.option("--ch-user", default=None, help="ClickHouse user")
@click.option("--ch-password", default=None, help="ClickHouse password")
@click.option("--ch-database", default=None, help="ClickHouse database")
@click.option("--ch-table", default=None, help="ClickHouse table name")
@click.option(
    "--follow",
    is_flag=True,
    default=False,
    help="Follow mode: auto-detect from-block from last stored trade (requires ClickHouse)",
)
def main(
    config: str | None,
    url: str | None,
    wallet_address: str | None,
    api_key: str | None,
    to_block: int | None,
    from_block: int | None,
    full: bool,
    log_level: str | None,
    to_json: bool,
    ch_host: str | None,
    ch_port: int | None,
    ch_user: str | None,
    ch_password: str | None,
    ch_database: str | None,
    ch_table: str | None,
    follow: bool,
) -> None:
    settings = load_settings(config)
    apply_settings(settings)

    def _resolve(value: str | int | None, field: str) -> str | int:
        return value if value is not None else getattr(settings, field)

    url = _resolve(url, "alchemy_url")
    api_key = _resolve(api_key, "alchemy_api_key")
    wallet_address = _resolve(wallet_address, "wallet_address")
    log_level = _resolve(log_level, "log_level")
    ch_host = _resolve(ch_host, "clickhouse_host")
    ch_port = int(_resolve(ch_port, "clickhouse_port"))
    ch_user = _resolve(ch_user, "clickhouse_user")
    ch_password = _resolve(ch_password, "clickhouse_password")
    ch_database = _resolve(ch_database, "clickhouse_database")
    ch_table = _resolve(ch_table, "clickhouse_table")

    if not wallet_address:
        raise click.UsageError(
            "Wallet address required via -w/--wallet-address, YAML config, or WALLET_ADDRESS env var"
        )
    if not api_key:
        raise click.UsageError("API key required via -k/--api-key, YAML config, or ALCHEMY_API_KEY env var")

    logging.basicConfig(level=str(log_level).upper())
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
        from_block = from_block or 0

    logging.info("Scanning blocks %s to %s", hex(from_block), to_block)

    if full:
        transactions = scan_blocks_range(w3, wallet_address, from_block, to_block)
    else:
        alchemy = AlchemyClient(rpc_url)
        blocks = alchemy.get_blocks_for_address(wallet_address, from_block, to_block, "fromAddress")
        blocks += alchemy.get_blocks_for_address(wallet_address, from_block, to_block, "toAddress")
        transactions = scan_specific_blocks(w3, wallet_address, sorted(set(blocks)))

    logging.info("Found %d transaction batches", len(transactions))
    trades = create_trades(w3, transactions, wallet_address, pairs=list(settings.pairs))
    logging.info("Created %d trades", len(trades))

    if to_json:
        export_to_json(trades)
    else:
        export_to_clickhouse(trades, ch_host, ch_port, ch_user, ch_password, ch_database, ch_table)


if __name__ == "__main__":
    main()
