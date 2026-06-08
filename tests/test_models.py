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


def test_transaction_value_eth():
    tx = Transaction(
        hash="0xh",
        from_address="0xfrom",
        to_address="0xto",
        value=10**18,
        block=1,
        event_logs=[],
    )
    assert tx.value_eth == 1.0


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
        trade_timestamp=1000,
        block_number=1,
        amount_eth=1.0,
        amount_usdc=2000.0,
        eth_sender="0xs",
        eth_receiver="0xr",
        token="USD Coin",
        token_address="0xaddr",
        token_sender="0xts",
        token_receiver="0xtr",
        price=2000.0,
        type="BUY",
    )
    d = trade.to_dict()
    assert d["transaction_hash"] == "0xh"
    assert d["price"] == 2000.0
    assert d["type"] == "BUY"
