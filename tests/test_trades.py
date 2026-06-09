from unittest.mock import MagicMock

from web3 import Web3

from trade_tracker.config import TradePair
from trade_tracker.models import EventLog, Transaction
from trade_tracker.trades import create_trades

SAMPLE_WALLET = "0x1234567890123456789012345678901234567890"
OTHER_WALLET = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
BASE_TOKEN = "0x4200000000000000000000000000000000000006"
QUOTE_TOKEN = "0x0b2c639c533813f4aa9d7837caf62653d097ff85"

PAIRS = [
    TradePair(
        name="ETH/USDC",
        base_token=BASE_TOKEN,
        quote_token=QUOTE_TOKEN,
        base_decimals=18,
        quote_decimals=6,
    ),
]


def _checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)


def _make_tx(
    event_logs: list[EventLog],
    value: int = 0,
    from_addr: str = SAMPLE_WALLET,
    to_addr: str = OTHER_WALLET,
) -> Transaction:
    return Transaction(
        hash="0xdeadbeef",
        from_address=from_addr,
        to_address=to_addr,
        value=value,
        block=100,
        event_logs=event_logs,
        timestamp=1000,
    )


def test_create_trades_buy():
    """Wallet sends quote (USDC), receives base (WETH) → BUY"""
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum

    logs = [
        EventLog(
            token_address=QUOTE_TOKEN,
            sender=SAMPLE_WALLET,
            receiver=OTHER_WALLET,
            amount=2_000_000_000,  # 2000 USDC (6 decimals)
            event_type="TRANSFER",
        ),
        EventLog(
            token_address=BASE_TOKEN,
            sender=OTHER_WALLET,
            receiver=SAMPLE_WALLET,
            amount=1_000_000_000_000_000_000,  # 1 ETH (18 decimals)
            event_type="TRANSFER",
        ),
    ]
    tx = _make_tx(logs, value=0)
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET, pairs=PAIRS)
    assert len(trades) == 1
    assert trades[0].type == "BUY"
    assert trades[0].pair_name == "ETH/USDC"
    assert trades[0].amount_quote == 2000.0
    assert trades[0].amount_base == 1.0
    assert trades[0].price == 2000.0
    assert trades[0].sender == SAMPLE_WALLET


def test_create_trades_sell():
    """Wallet sends base (WETH), receives quote (USDC) → SELL"""
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum

    logs = [
        EventLog(
            token_address=BASE_TOKEN,
            sender=SAMPLE_WALLET,
            receiver=OTHER_WALLET,
            amount=500_000_000_000_000_000,  # 0.5 ETH
            event_type="TRANSFER",
        ),
        EventLog(
            token_address=QUOTE_TOKEN,
            sender=OTHER_WALLET,
            receiver=SAMPLE_WALLET,
            amount=1_000_000_000,  # 1000 USDC
            event_type="TRANSFER",
        ),
    ]
    tx = _make_tx(logs, value=0)
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET, pairs=PAIRS)
    assert len(trades) == 1
    assert trades[0].type == "SELL"
    assert trades[0].amount_quote == 1000.0
    assert trades[0].amount_base == 0.5
    assert trades[0].price == 2000.0


def test_create_trades_no_match_skipped():
    """Only one token moves → no trade"""
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum

    logs = [
        EventLog(
            token_address=QUOTE_TOKEN,
            sender=SAMPLE_WALLET,
            receiver=OTHER_WALLET,
            amount=100_000_000,
            event_type="TRANSFER",
        ),
    ]
    tx = _make_tx([log for log in logs])
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET, pairs=PAIRS)
    assert len(trades) == 0


def test_create_trades_no_events_skipped():
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum
    tx = _make_tx([], value=0)
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET, pairs=PAIRS)
    assert len(trades) == 0


def test_create_trades_multiple_pairs():
    """Transaction involves two different pairs → two trades"""
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum

    other_base = "0x4200000000000000000000000000000000000042"  # OP
    pairs = [
        TradePair(name="ETH/USDC", base_token=BASE_TOKEN, quote_token=QUOTE_TOKEN),
        TradePair(name="OP/USDC", base_token=other_base, quote_token=QUOTE_TOKEN),
    ]

    logs = [
        # ETH/USDC leg: send USDC, receive WETH
        EventLog(
            token_address=QUOTE_TOKEN,
            sender=SAMPLE_WALLET,
            receiver=OTHER_WALLET,
            amount=1_000_000_000,
            event_type="TRANSFER",
        ),
        EventLog(
            token_address=BASE_TOKEN,
            sender=OTHER_WALLET,
            receiver=SAMPLE_WALLET,
            amount=1_000_000_000_000_000_000,
            event_type="TRANSFER",
        ),
        # OP/USDC leg: send OP, receive USDC
        EventLog(
            token_address=other_base,
            sender=SAMPLE_WALLET,
            receiver=OTHER_WALLET,
            amount=2_000_000_000_000_000_000_000,
            event_type="TRANSFER",
        ),
        EventLog(
            token_address=QUOTE_TOKEN,
            sender=OTHER_WALLET,
            receiver=SAMPLE_WALLET,
            amount=500_000_000,  # 500 USDC
            event_type="TRANSFER",
        ),
    ]
    tx = _make_tx(logs, value=0)
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET, pairs=pairs)
    assert len(trades) == 2
    trade_types = {t.pair_name: t.type for t in trades}
    assert trade_types["ETH/USDC"] == "BUY"
    assert trade_types["OP/USDC"] == "SELL"
