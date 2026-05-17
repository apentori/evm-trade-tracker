#!/usr/bin/env python
import requests
from web3 import Web3
from eth_abi import decode
import click
import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import logging

DEFAULT_URL="https://opt-mainnet.g.alchemy.com/v2"

@dataclass
class EventLog:
    token_address: str
    sender: str
    receiver: str
    amount: str

@dataclass
class Transaction:
    hash: str
    from_address: str
    to_address: str
    value: int
    block: int
    event_logs: List

    @property
    def value_eth(self):
        return Web3.from_wei(self.value, 'ether')

    def add_event_logs(self, event):
        self.event_logs.append(event)

def print_json(data):
    dict_data = [asdict(obj) for obj in data]
    with open("transactions.json", 'w', encoding='utf-8') as f:
        json.dump(dict_data, f, indent=4)

def extract_event_logs(trx_log):
    sender = "0x" + trx_log['topics'][0].hex()[-40:]
    receiver = "0x" + trx_log['topics'][1].hex()[-40:]
    if len(trx_log['topics']) > 2:
        sender = "0x" + trx_log['topics'][1].hex()[-40:]
        receiver = "0x" + trx_log['topics'][2].hex()[-40:]
    logging.debug(f"Raw Log{trx_log}")
    return EventLog(
        token_address=trx_log['address'],
        sender=sender,
        receiver=receiver,
        amount=Web3.to_int(hexstr=trx_log['data'].hex())
    )

def get_block_trx(w3, block_num, target_address):
    blk_trx = []
    block = w3.eth.get_block(block_num, full_transactions=True)
    for tx in block.transactions:
        tx_hash = f"0x{tx['hash'].hex()}"
        # Limit only to the trx from the wallet to monitore
        if tx['from'] == target_address or tx['to'] == target_address:
            logging.info(f"Found trx with involved address - hash {tx_hash}")
            # Having the TRX
            # Call for the receipt
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            events = []
            for log in receipt['logs']:
                event = extract_event_logs(log)
                logging.debug(f"log from {event.sender} to {event.receiver}")
                if w3.to_checksum_address(event.sender) == target_address or w3.to_checksum_address(event.receiver) == target_address:
                    logging.info(f"Adding event log {event}")
                    events.append(event)
            tx_obj = Transaction(
                hash=tx_hash,
                from_address=tx['from'],
                to_address=tx['to'],
                value=tx['value'],
                block=block_num,
                event_logs=events
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

def get_block_alchemy(rpc_url, wallet_address, from_block, to_block):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "alchemy_getAssetTransfers",
        "params": [
            {
                "fromBlock": f"{from_block}",
                "toBlock": f"{to_block}",
                "toAddress": f"{wallet_address}",
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
    logging.info(f"List of blocks found {unique_blocks_list}")
    return unique_blocks_list

@click.command()
@click.option('-u', '--url', default=DEFAULT_URL, help="Alchemy URL")
@click.option('-w', '--wallet-address', required=True, help='Wallet address to scan')
@click.option('-k','--api-key', required=True, help='API key')
@click.option('--to-block', type=int, default=None, help='Latest block number to scan (default: current block)')
@click.option('--from-block', type=int, default="0x0", help='From block number to scan (default: current block)')
@click.option('-f', '--full', default=False, help='Should the ')
@click.option('--log-level', '-l', default="INFO", help='Log Level')
def main(url, wallet_address, api_key, to_block, from_block, full, log_level):
    logging.basicConfig(level=log_level.upper())
    rpc_url = f"{url}/{api_key}"
    logging.info(rpc_url)
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if to_block is None:
        to_block = w3.eth.block_number
    transactions = []
    logging.info(f"{hex(from_block)} - {to_block}")
    if full:
        transactions = get_full_transactions(w3, wallet_address, from_block, to_block)
    else:
        blocks_list = get_block_alchemy(rpc_url, wallet_address, hex(from_block),
                                        hex(to_block))
        transactions = get_transactions_special_block(w3, wallet_address, blocks_list)
    logging.info(f"Found {len(transactions)} transactions:")
    for trx in transactions:
        logging.info(trx)

    print_json(transactions)

if __name__ == "__main__":
    main()
