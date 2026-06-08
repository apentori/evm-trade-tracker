from unittest.mock import MagicMock

from web3 import Web3

from trade_tracker.cache import TokenCache
from trade_tracker.config import USDC_ADDRESS, WETH_ADDRESS
from trade_tracker.models import EventLog, Transaction
from trade_tracker.trades import create_trades

SAMPLE_WALLET = "0x1234567890123456789012345678901234567890"


def _checksum(addr: str) -> str:
    return Web3.to_checksum_address(addr)


def _mock_token_cache() -> TokenCache:
    cache = MagicMock(spec=TokenCache)
    cache.get_decimals.return_value = 6
    cache.get_name.return_value = "USD Coin"
    return cache


def _make_tx(
    event_logs: list[EventLog],
    value: int = 0,
    from_addr: str = SAMPLE_WALLET,
    to_addr: str = "0x2222222222222222222222222222222222222222",
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
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum

    logs = [
        EventLog(
            token_address=USDC_ADDRESS,
            sender=SAMPLE_WALLET,
            receiver="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            amount=2_000_000_000,  # 2000 USDC (6 decimals)
            event_type="TRANSFER",
        ),
        EventLog(
            token_address=WETH_ADDRESS,
            sender="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            receiver=SAMPLE_WALLET,
            amount=1_000_000_000_000_000_000,  # 1 WETH (18 decimals)
            event_type="WITHDRAWAL",
        ),
    ]
    tx = _make_tx(logs, value=0)
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET, token_cache=_mock_token_cache())
    assert len(trades) == 1
    assert trades[0].type == "BUY"
    assert trades[0].amount_usdc == 2000.0


def test_create_trades_sell():
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum

    logs = [
        EventLog(
            token_address=USDC_ADDRESS,
            sender="0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            receiver=SAMPLE_WALLET,
            amount=1_000_000_000,  # 1000 USDC
            event_type="TRANSFER",
        ),
        EventLog(
            token_address=WETH_ADDRESS,
            sender=SAMPLE_WALLET,
            receiver="0xcccccccccccccccccccccccccccccccccccccccc",
            amount=500_000_000_000_000_000,  # 0.5 WETH
            event_type="TRANSFER",
        ),
    ]
    tx = _make_tx(logs, value=0)
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET, token_cache=_mock_token_cache())
    assert len(trades) == 1
    assert trades[0].type == "SELL"
    assert trades[0].amount_usdc == 1000.0


def test_create_trades_no_usdc_skipped():
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum
    tx = _make_tx([], value=0)
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET)
    assert len(trades) == 0


def test_create_trades_empty_event_logs_skipped():
    w3 = MagicMock(spec=Web3)
    w3.to_checksum_address = _checksum
    log = EventLog(
        token_address="0xdddddddddddddddddddddddddddddddddddddddd",
        sender=SAMPLE_WALLET,
        receiver="0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
        amount=100,
        event_type="TRANSFER",
    )
    tx = _make_tx([log])
    trades = create_trades(w3, [[tx]], SAMPLE_WALLET)
    assert len(trades) == 0
