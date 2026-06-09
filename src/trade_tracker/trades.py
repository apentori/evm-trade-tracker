from __future__ import annotations

import logging

from web3 import Web3

from trade_tracker.config import TradePair
from trade_tracker.models import Trade, Transaction


def create_trades(
    w3: Web3,
    transactions: list[list[Transaction]],
    wallet_address: str,
    pairs: list[TradePair] | None = None,
) -> list[Trade]:
    if pairs is None:
        pairs = [
            TradePair(
                name="ETH/USDC",
                base_token="0x4200000000000000000000000000000000000006",
                quote_token="0x0b2c639c533813f4aa9d7837caf62653d097ff85",
                base_decimals=18,
                quote_decimals=6,
            ),
        ]

    checksum_wallet = w3.to_checksum_address(wallet_address)

    # All token addresses we care about across all pairs
    tracked = set()
    for p in pairs:
        tracked.add(p.base_token.lower())
        tracked.add(p.quote_token.lower())

    trades: list[Trade] = []

    for tx_list in transactions:
        for tx in tx_list:
            if not tx.event_logs:
                logging.warning("No events in transaction %s", tx.hash)
                continue

            relevant = [log for log in tx.event_logs if log.token_address.lower() in tracked]
            if not relevant:
                continue

            for pair in pairs:
                base_addr = pair.base_token.lower()
                quote_addr = pair.quote_token.lower()

                # Gross flows for this pair: how much base/quote the wallet sent/received
                base_received = 0
                base_sent = 0
                quote_received = 0
                quote_sent = 0

                for log in relevant:
                    addr = log.token_address.lower()
                    log_sender = w3.to_checksum_address(log.sender)
                    log_receiver = w3.to_checksum_address(log.receiver)

                    if addr == base_addr:
                        if log_sender == checksum_wallet:
                            base_sent += log.amount
                        if log_receiver == checksum_wallet:
                            base_received += log.amount
                    elif addr == quote_addr:
                        if log_sender == checksum_wallet:
                            quote_sent += log.amount
                        if log_receiver == checksum_wallet:
                            quote_received += log.amount

                # BUY: wallet sends quote, receives base
                if quote_sent > 0 and base_received > 0:
                    amount_base = base_received
                    amount_quote = quote_sent
                    trade_type = "BUY"
                # SELL: wallet sends base, receives quote
                elif base_sent > 0 and quote_received > 0:
                    amount_base = base_sent
                    amount_quote = quote_received
                    trade_type = "SELL"
                else:
                    continue

                base_dec = pair.base_decimals
                quote_dec = pair.quote_decimals
                amount_base_dec = amount_base / (10**base_dec)
                amount_quote_dec = amount_quote / (10**quote_dec)

                if amount_base_dec == 0:
                    continue

                trades.append(
                    Trade(
                        transaction_hash=tx.hash,
                        trade_timestamp=tx.timestamp,
                        block_number=tx.block,
                        pair_name=pair.name,
                        base_token=pair.base_token,
                        quote_token=pair.quote_token,
                        amount_base=round(amount_base_dec, 18),
                        amount_quote=amount_quote_dec,
                        price=amount_quote_dec / amount_base_dec,
                        type=trade_type,
                        sender=wallet_address,
                    )
                )

    return trades
