from __future__ import annotations

import logging

from web3 import Web3

from trade_tracker.config import EVENT_TOPIC_TYPE, NULL_ADDRESS, SWAP_ABI_NAMES, SWAP_ABI_TYPES
from trade_tracker.models import EventLog, Transaction


def hex_to_int(hex_str: str, signed: bool = False) -> int:
    if not hex_str:
        return 0
    hex_str = hex_str[2:] if hex_str.startswith(("0x", "0X")) else hex_str
    if len(hex_str) % 2 != 0:
        hex_str = "0" + hex_str
    value = int(hex_str, 16)
    if not signed:
        return value
    bit_length = len(hex_str) * 4
    if bit_length > 0 and (value >> (bit_length - 1)) & 1:
        value -= 1 << bit_length
    return value


def extract_event_log(log: dict, target_address: str) -> EventLog | None:
    log_address = log["address"]
    topic0 = "0x" + log["topics"][0].hex()
    event_type = EVENT_TOPIC_TYPE.get(topic0)
    if event_type is None:
        logging.debug("Unknown event topic %s", topic0)
        return None

    if event_type == "TRANSFER":
        if len(log["topics"]) < 3:
            return None
        from_addr = "0x" + log["topics"][1].hex()[-40:]
        to_addr = "0x" + log["topics"][2].hex()[-40:]
        amount = Web3.to_int(hexstr=log["data"].hex())
        return EventLog(
            token_address=log_address,
            sender=from_addr,
            receiver=to_addr,
            amount=amount,
            event_type=event_type,
        )

    if event_type == "SWAP":
        hex_data = log["data"].hex()
        chunks = [hex_data[i : i + 64] for i in range(0, len(hex_data), 64)]
        for chunk, name, type_ in zip(chunks, SWAP_ABI_NAMES, SWAP_ABI_TYPES):
            is_signed = type_.startswith("int")
            value = hex_to_int("0x" + chunk, is_signed)
            logging.debug("Swap %s (%s): %s", name, type_, value)
        return None

    if event_type == "WITHDRAWAL":
        to_addr = "0x" + log["topics"][1].hex()[-40:]
        amount = Web3.to_int(hexstr=log["data"].hex())
        return EventLog(
            token_address=log_address,
            sender=NULL_ADDRESS,
            receiver=target_address,
            amount=amount,
            event_type=event_type,
        )

    return None


def get_block_transactions(w3: Web3, block_num: int, target_address: str) -> list[Transaction]:
    if isinstance(block_num, str):
        block_num = int(block_num, 16)

    block = w3.eth.get_block(block_num, full_transactions=True)
    block_timestamp = block.get("timestamp", 0)
    results: list[Transaction] = []

    for tx in block.transactions:
        tx_hash = "0x" + tx["hash"].hex()
        if tx["from"] != target_address and tx["to"] != target_address:
            continue

        receipt = w3.eth.get_transaction_receipt(tx_hash)
        events = []
        for log_entry in receipt["logs"]:
            event = extract_event_log(log_entry, target_address)
            if event is None:
                continue
            checksummed_sender = w3.to_checksum_address(event.sender)
            checksummed_receiver = w3.to_checksum_address(event.receiver)
            if checksummed_sender == target_address or checksummed_receiver == target_address:
                events.append(event)

        results.append(
            Transaction(
                hash=tx_hash,
                from_address=tx["from"],
                to_address=tx["to"],
                value=tx["value"],
                block=block_num,
                event_logs=events,
                timestamp=block_timestamp,
            )
        )
    return results


def scan_blocks_range(w3: Web3, wallet_address: str, start_block: int, end_block: int) -> list[list[Transaction]]:
    target_address = w3.to_checksum_address(wallet_address)
    tx_history: list[list[Transaction]] = []
    for block_num in range(start_block, end_block + 1):
        tx_history.append(get_block_transactions(w3, block_num, target_address))
        if block_num % 10 == 0:
            logging.info("Current Block: %s", block_num)
    return tx_history


def scan_specific_blocks(w3: Web3, wallet_address: str, block_list: list[int]) -> list[list[Transaction]]:
    target_address = w3.to_checksum_address(wallet_address)
    tx_history: list[list[Transaction]] = []
    for block in block_list:
        logging.info("Looking at block %s", block)
        tx_history.append(get_block_transactions(w3, block, target_address))
    return tx_history
