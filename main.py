#!/usr/bin/env python
import requests
from web3 import Web3
import click
import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import logging
from clickhouse_driver import Client

DEFAULT_URL="https://opt-mainnet.g.alchemy.com/v2"

@dataclass
class EventLog:
    token_address: str
    sender: str
    receiver: str
    amount: str
    event_type: str

@dataclass
class Transaction:
    hash: str
    from_address: str
    to_address: str
    value: int
    block: int
    event_logs: List
    timestamp: int = 0

    @property
    def value_eth(self):
        return Web3.from_wei(self.value, 'ether')

    def add_event_logs(self, event):
        self.event_logs.append(event)


_token_cache = {}

def get_token_name(w3, token_address):
    if token_address in _token_cache and 'name' in _token_cache[token_address]:
        return _token_cache[token_address]['name']
    try:
        contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=[{"constant":True,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"type":"function"}])
        name = contract.functions.name().call()
        if token_address not in _token_cache:
            _token_cache[token_address] = {}
        _token_cache[token_address]['name'] = name
        return name
    except Exception as e:
        logging.warning(f"Failed to fetch token name for {token_address}: {e}")
        return "Unknown"

def get_token_decimals(w3, token_address):
    if token_address in _token_cache and 'decimals' in _token_cache[token_address]:
        return _token_cache[token_address]['decimals']
    try:
        contract = w3.eth.contract(address=w3.to_checksum_address(token_address), abi=[{"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}])
        decimals = contract.functions.decimals().call()
        if token_address not in _token_cache:
            _token_cache[token_address] = {}
        _token_cache[token_address]['decimals'] = decimals
        return decimals
    except Exception as e:
        logging.warning(f"Failed to fetch token decimals for {token_address}: {e}")
        return 18


@dataclass
class Trade:
    transaction_hash: str
    trade_timestamp: int
    block_number: int
    amount_eth: float
    amount_usdc: float
    eth_sender: str
    eth_receiver: str
    token: str
    token_address: str
    token_sender: str
    token_receiver: str
    price: float
    type: str


def create_trades(w3, transactions, wallet_address):
    trades = []
    checksum_wallet = w3.to_checksum_address(wallet_address)

    # Known token addresses on Optimism
    USDC_ADDRESS = '0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85'.lower()
    USDC_OLD_ADDRESS = '0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1'.lower()
    WETH_OLD_ADDRESS = '0x4200000000000000000000000000000000000042'.lower()
    WETH_ADDRESS = "0x4200000000000000000000000000000000000006".lower()

    tracked_tokens = [USDC_ADDRESS, USDC_OLD_ADDRESS, WETH_ADDRESS]

    failed_trx = []
    for tx_list in transactions:
        for tx in tx_list:
            logging.info(f"Creating trade for transaction {tx.hash}")
            if not tx.event_logs:
                logging.warning(f"No events in transaction {tx.hash}")
                continue

            # Filter to tracked tokens only
            filtered_logs = [log for log in tx.event_logs if log.token_address.lower() in tracked_tokens]
            if not filtered_logs:
                continue

            # Track per-token amounts sent/received by the wallet
            sent = {}
            received = {}
            token_sender = ""
            token_receiver = ""

            trade_type = "BUY" if any(event.event_type == "WITHDRAWAL" for event in filtered_logs) else "SELL"

            for log in filtered_logs:
                token_adr = log.token_address.lower()
                log_sender = w3.to_checksum_address(log.sender)
                log_receiver = w3.to_checksum_address(log.receiver)

                if log_sender == checksum_wallet:
                    sent[token_adr] = sent.get(token_adr, 0) + log.amount
                    token_sender = log.sender
                if log_receiver == checksum_wallet:
                    received[token_adr] = received.get(token_adr, 0) + log.amount
                    token_receiver = log.receiver

                logging.debug(f"token {token_adr} - sent {sent.get(token_adr, 0)} / received {received.get(token_adr, 0)}")

            # Extract USDC and WETH amounts
            sent_usdc = sent.get(USDC_ADDRESS, 0) or sent.get(USDC_OLD_ADDRESS, 0)
            received_usdc = received.get(USDC_ADDRESS, 0) or received.get(USDC_OLD_ADDRESS, 0)
            sent_weth = sent.get(WETH_ADDRESS, 0)
            received_weth = received.get(WETH_ADDRESS, 0)

            # Determine which USDC token was used
            usdc_address = USDC_ADDRESS if (sent.get(USDC_ADDRESS, 0) or received.get(USDC_ADDRESS, 0)) else USDC_OLD_ADDRESS
            usdc_amount_raw = sent_usdc or received_usdc

            if usdc_amount_raw == 0:
                logging.warning(f"No usdc in the transaction {tx.hash}")
                failed_trx.append(tx)
                continue

            # Determine trade type and ETH amount
            if received_usdc > 0:
                eth_amount = (tx.value / 1e18) + (sent_weth / 1e18)
            else:
                eth_amount = received_weth / 1e18

            token_name = "USD Coin" if usdc_address == USDC_ADDRESS else get_token_name(w3, usdc_address)
            token_decimals = get_token_decimals(w3, usdc_address)
            amount_usdc = usdc_amount_raw / (10 ** token_decimals)
            if eth_amount == 0:
                logging.error(f"error with transaction {tx.hash}")
                failed_trx.append(tx)
                continue

            trade = Trade(
                transaction_hash=tx.hash,
                trade_timestamp=tx.timestamp,
                block_number=tx.block,
                amount_eth=eth_amount,
                amount_usdc=amount_usdc,
                eth_sender=tx.from_address,
                eth_receiver=tx.to_address,
                token=token_name,
                token_address=usdc_address,
                token_sender=token_sender,
                token_receiver=token_receiver,
                price= amount_usdc / eth_amount,
                type=trade_type
            )
            trades.append(trade)
    logging.info(f"List of failed trades building:")
    for failed in failed_trx:
        logging.info(f"{failed.hash}")
    return trades

EVENT_TOPIC_TYPE = {
        "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f": "SWAP",
        "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": "TRANSFERT",
        "0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65": "WITHDRAWAL"
        }


def print_json(data):
    dict_data = [asdict(obj) for obj in data]
    with open("trades.json", 'w', encoding='utf-8') as f:
        json.dump(dict_data, f, indent=4)


def export_to_clickhouse(trades, host, port, user, password, database, table):
    dict_data = [asdict(obj) for obj in trades]
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
    create_query = f"""
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
    client.execute(create_query)
    client.execute(f'INSERT INTO {table} VALUES', dict_data)
    client.disconnect()
    logging.info(f"Exported {len(dict_data)} trades to ClickHouse ({database}.{table})")


def hex_to_int(hex_str: str, signed: bool = False) -> int:
    if not hex_str:
        return 0

    # Remove '0x' prefix and pad to even length
    hex_str = hex_str[2:] if hex_str.startswith(('0x', '0X')) else hex_str
    if len(hex_str) % 2 != 0:
        hex_str = '0' + hex_str  # Pad odd-length strings (e.g., "0x1" → "01")

    value = int(hex_str, 16)

    if not signed:
        return value

    # Calculate bit length (4 bits per hex char)
    bit_length = len(hex_str) * 4

    # Check if the MSB is set (negative in two's complement)
    if bit_length > 0 and (value >> (bit_length - 1)) & 1:
        value -= (1 << bit_length)  # Subtract 2^bit_length to get negative value

    return value


def extract_event_logs(trx_log, target_address):
    log_address = trx_log['address']
    topic0 = "0x" + trx_log['topics'][0].hex()
    if topic0 not in EVENT_TOPIC_TYPE:
        logging.info(f"No type found for {topic0}")
        return None
    event_type = EVENT_TOPIC_TYPE[topic0]
    logging.info(f"-- Event {event_type} with Address {log_address}, topic0 {topic0}")

    if event_type == "TRANSFERT":
        # ERC20 Transfer(from, to, amount)
        # topics[0] = event sig, topics[1] = from, topics[2] = to
        if len(trx_log['topics']) < 3:
            return None
        l_from = "0x" + trx_log['topics'][1].hex()[-40:]
        l_to = "0x" + trx_log['topics'][2].hex()[-40:]
        l_amount = Web3.to_int(hexstr=trx_log['data'].hex())
        logging.debug(f"Transfer from {l_from} to {l_to} - {l_amount}")
        return EventLog(
            token_address=log_address,
            sender=l_from,
            receiver=l_to,
            amount=l_amount,
            event_type=event_type
        )

    if event_type == "SWAP":
        logging.debug("This is a Swap")
        hex_data = trx_log['data'].hex()
        types = ['int128', 'int128', 'uint160', 'uint128', 'int24', 'uint24']
        names = ['amount0', 'amount1', 'sqrtPriceX96', 'liquidity', 'tick', 'fee']
        chunks = [hex_data[i:i+64] for i in range(0, len(hex_data), 64)]
        for i, (chunk, name, type_) in enumerate(zip(chunks, names, types)):
            hex_chunk = "0x" + chunk
            is_signed = type_.startswith('int')
            value = hex_to_int(hex_chunk, is_signed)
            logging.debug(f"Swap {name} ({type_}): {value}")
        return None

    if event_type == "WITHDRAWAL":
        # WETH Withdrawal(to, amount) — emitted when WETH is unwrapped to ETH
        l_to = "0x" + trx_log['topics'][1].hex()[-40:]
        l_amount = Web3.to_int(hexstr=trx_log['data'].hex())
        logging.debug(f"WETH Withdrawal to {l_to} - {l_amount}")
        return EventLog(
            token_address=log_address,
            sender="0x0000000000000000000000000000000000000000",
            receiver=target_address,
            amount=l_amount,
            event_type=event_type
        )

def get_block_trx(w3, block_num, target_address):
    blk_trx = []
    if isinstance(block_num, str):
        block_num = int(block_num, 16)
    logging.debug(f"Calling for block {block_num}")
    block = w3.eth.get_block(block_num, full_transactions=True)
    block_timestamp = block.get('timestamp', 0)
    for tx in block.transactions:
        tx_hash = f"0x{tx['hash'].hex()}"
        # Limit only to the trx from the wallet to monitore
        if tx['from'] == target_address or tx['to'] == target_address:
            logging.debug(f"Found trx with involved address - hash {tx_hash}")
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            events = []
            for log in receipt['logs']:
                event = extract_event_logs(log, target_address)
                if event == None:
                    logging.warning("logs without enough data")
                    continue
                logging.debug(f"log from {event.sender} to {event.receiver}")
                if w3.to_checksum_address(event.sender) == target_address or w3.to_checksum_address(event.receiver) == target_address:
                    logging.debug(f"Adding event log {event}")
                    events.append(event)
            tx_obj = Transaction(
                hash=tx_hash,
                from_address=tx['from'],
                to_address=tx['to'],
                value=tx['value'],
                block=block_num,
                event_logs=events,
                timestamp=block_timestamp
            )
            blk_trx.append(tx_obj)
    return blk_trx


def get_full_transactions(w3, wallet_address, start_block, end_block):
    w3.strict_bytes_type_checking = False
    target_address = w3.to_checksum_address(wallet_address)
    tx_history = []
    logging.info(f"Scanning blocks {start_block} to {end_block}...")
    for block_num in range(start_block, end_block + 1):
        tx_history.append(get_block_trx(w3, block_num, target_address))
        if block_num % 10 == 0:
            logging.info(f"Current Block: {block_num}")
    return tx_history

def get_transactions_special_block(w3, wallet_address, block_list):
    w3.strict_bytes_type_checking = False
    target_address = w3.to_checksum_address(wallet_address)
    tx_history = []
    for block in block_list:
        logging.info(f"Looking at block {block}")
        tx_history.append(get_block_trx(w3, block, target_address))
    return tx_history

def get_block_alchemy(rpc_url, wallet_address, from_block, to_block, direction):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "alchemy_getAssetTransfers",
        "params": [
            {
                "fromBlock": f"{from_block}",
                "toBlock": f"{to_block}",
                direction: f"{wallet_address}",
                "excludeZeroValue": True,
                "withMetadata": True,
                "category": ["erc20"]
            }
        ]
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(rpc_url, json=payload, headers=headers)
    transfers = response.json()["result"]["transfers"]

    unique_blocks = set(transfer["blockNum"] for transfer in transfers)
    unique_blocks_list = list(unique_blocks)
    logging.info(f"{unique_blocks_list} blocks found {direction}")
    return unique_blocks_list

@click.command()
@click.option('-u', '--url', default=DEFAULT_URL, help="Alchemy URL")
@click.option('-w', '--wallet-address', required=True, help='Wallet address to scan')
@click.option('-k','--api-key', required=True, help='API key')
@click.option('--to-block', type=int, default=None, help='Latest block number to scan (default: current block)')
@click.option('--from-block', type=int, default="0", help='From block number to scan (default: current block)')
@click.option('-f', '--full', default=False, help='Should the ')
@click.option('--log-level', '-l', default="INFO", help='Log Level')
@click.option('--to-json', is_flag=True, default=False, help='Export to trades.json instead of ClickHouse')
@click.option('--ch-host', default='localhost', help='ClickHouse host (default: localhost)')
@click.option('--ch-port', type=int, default=9000, help='ClickHouse port (default: 9000)')
@click.option('--ch-user', default='default', help='ClickHouse user (default: default)')
@click.option('--ch-password', default='', help='ClickHouse password')
@click.option('--ch-database', default='default', help='ClickHouse database (default: default)')
@click.option('--ch-table', default='trades', help='ClickHouse table name (default: trades)')
@click.option('--follow', is_flag=True, default=False, help='Follow mode: auto-detect from-block from last stored trade (requires ClickHouse)')
def main(url, wallet_address, api_key, to_block, from_block, full, log_level, to_json, ch_host, ch_port, ch_user, ch_password, ch_database, ch_table, follow):
    logging.basicConfig(level=log_level.upper())
    rpc_url = f"{url}/{api_key}"
    logging.info(rpc_url)
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if follow:
        if to_json:
            raise click.ClickException("--follow requires ClickHouse mode, not --to-json")
        client = Client(
            host=ch_host,
            port=ch_port,
            user=ch_user,
            password=ch_password,
            database=ch_database,
        )
        rows = client.execute(f"SELECT MAX(block_number) FROM {ch_database}.{ch_table}")
        last_block = rows[0][0] if rows else 0
        client.disconnect()
        from_block = (last_block or 0) + 1
        to_block = w3.eth.block_number
    else:
        if to_block is None:
            to_block = w3.eth.block_number
    transactions = []
    logging.info(f"{hex(from_block)} - {to_block}")
    if full:
        transactions = get_full_transactions(w3, wallet_address, from_block, to_block)
    else:
        blocks_list = get_block_alchemy(rpc_url, wallet_address, hex(from_block), hex(to_block), "fromAddress") + get_block_alchemy(rpc_url, wallet_address, hex(from_block), hex(to_block), "toAddress")
        transactions = get_transactions_special_block(w3, wallet_address, blocks_list)
    logging.info(f"Found {len(transactions)} transactions:")
    trades = create_trades(w3, transactions, wallet_address)
    logging.info(f"Created {len(trades)} trades")
    if to_json:
        print_json(trades)
    else:
        export_to_clickhouse(trades, ch_host, ch_port, ch_user, ch_password, ch_database, ch_table)

if __name__ == "__main__":
    main()
