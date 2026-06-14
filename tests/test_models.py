from datetime import datetime, timezone

from trade_tracker.models import EventLog, Trade, Transaction


def test_event_log_creation():
    log = EventLog(
        token_address="0xabc",
        sender="0xfrom",
        receiver="0xto",
        amount=1000,
        event_type="TRANSFER",
    )
    assert log.token_address == "0xabc"
    assert log.amount == 1000


def test_transaction_add_event_log():
    log = EventLog(token_address="0xabc", sender="0xf", receiver="0xt", amount=5, event_type="TRANSFER")
    tx = Transaction(
        hash="0xh",
        from_address="0xf",
        to_address="0xt",
        value=0,
        block=1,
        event_logs=[],
    )
    tx.add_event_log(log)
    assert len(tx.event_logs) == 1
    assert tx.event_logs[0] == log


def test_trade_to_dict():
    trade = Trade(
        transaction_hash="0xh",
        trade_datetime=datetime.fromtimestamp(1000, tz=timezone.utc),
        block_number=1,
        pair_name="ETH/USDC",
        base_token="0xbase",
        quote_token="0xquote",
        amount_base=1.0,
        amount_quote=2000.0,
        price=2000.0,
        type="BUY",
        sender="0xsender",
    )
    d = trade.to_dict()
    assert d["transaction_hash"] == "0xh"
    assert d["price"] == 2000.0
    assert d["type"] == "BUY"
    assert d["pair_name"] == "ETH/USDC"
    assert d["amount_base"] == 1.0
    assert d["amount_quote"] == 2000.0
    assert d["sender"] == "0xsender"
