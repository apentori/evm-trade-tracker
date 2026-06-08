from __future__ import annotations

import logging

from web3 import Web3

from trade_tracker.cache import TokenCache
from trade_tracker.config import (
    TRACKED_TOKENS,
    USDC_ADDRESS,
    USDC_OLD_ADDRESS,
    WETH_ADDRESS,
)
from trade_tracker.models import Trade, Transaction


def create_trades(
    w3: Web3,
    transactions: list[list[Transaction]],
    wallet_address: str,
    token_cache: TokenCache | None = None,
) -> list[Trade]:
    if token_cache is None:
        token_cache = TokenCache()

    checksum_wallet = w3.to_checksum_address(wallet_address)
    trades: list[Trade] = []
    failed_hashes: list[str] = []

    for tx_list in transactions:
        for tx in tx_list:
            if not tx.event_logs:
                logging.warning("No events in transaction %s", tx.hash)
                continue

            filtered_logs = [log for log in tx.event_logs if log.token_address.lower() in TRACKED_TOKENS]
            if not filtered_logs:
                continue

            sent: dict[str, int] = {}
            received: dict[str, int] = {}
            token_sender = ""
            token_receiver = ""

            has_withdrawal = any(event.event_type == "WITHDRAWAL" for event in filtered_logs)
            trade_type = "BUY" if has_withdrawal else "SELL"

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

            sent_usdc = sent.get(USDC_ADDRESS, 0) or sent.get(USDC_OLD_ADDRESS, 0)
            received_usdc = received.get(USDC_ADDRESS, 0) or received.get(USDC_OLD_ADDRESS, 0)
            sent_weth = sent.get(WETH_ADDRESS, 0)
            received_weth = received.get(WETH_ADDRESS, 0)

            usdc_address = (
                USDC_ADDRESS if (sent.get(USDC_ADDRESS, 0) or received.get(USDC_ADDRESS, 0)) else USDC_OLD_ADDRESS
            )
            usdc_amount_raw = sent_usdc or received_usdc

            if usdc_amount_raw == 0:
                logging.warning("No USDC in transaction %s", tx.hash)
                failed_hashes.append(tx.hash)
                continue

            if received_usdc > 0:
                eth_amount = (tx.value / 1e18) + (sent_weth / 1e18)
            else:
                eth_amount = received_weth / 1e18

            token_name = "USD Coin" if usdc_address == USDC_ADDRESS else token_cache.get_name(w3, usdc_address)
            token_decimals = token_cache.get_decimals(w3, usdc_address)
            amount_usdc = usdc_amount_raw / (10**token_decimals)

            if eth_amount == 0:
                logging.error("Error with transaction %s", tx.hash)
                failed_hashes.append(tx.hash)
                continue

            trade = Trade(
                transaction_hash=tx.hash,
                trade_timestamp=tx.timestamp,
                block_number=tx.block,
                amount_eth=round(eth_amount, 18),
                amount_usdc=amount_usdc,
                eth_sender=tx.from_address,
                eth_receiver=tx.to_address,
                token=token_name,
                token_address=usdc_address,
                token_sender=token_sender,
                token_receiver=token_receiver,
                price=amount_usdc / eth_amount,
                type=trade_type,
            )
            trades.append(trade)

    if failed_hashes:
        logging.info("Failed trades: %s", ", ".join(failed_hashes))
    return trades
