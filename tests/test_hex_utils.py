from trade_tracker.blockchain import hex_to_int


def test_hex_to_int_unsigned():
    assert hex_to_int("0x0") == 0
    assert hex_to_int("0x1") == 1
    assert hex_to_int("0xff") == 255
    assert hex_to_int("0x10") == 16


def test_hex_to_int_signed_positive():
    assert hex_to_int("0x0a", signed=True) == 10
    assert hex_to_int("0x7f", signed=True) == 127


def test_hex_to_int_signed_negative():
    assert hex_to_int("0x80", signed=True) == -128
    assert hex_to_int("0xff", signed=True) == -1


def test_hex_to_int_empty():
    assert hex_to_int("") == 0


def test_hex_to_int_no_prefix():
    assert hex_to_int("ff") == 255
    assert hex_to_int("0Xab") == 171


def test_hex_to_int_odd_length():
    assert hex_to_int("0x1") == 1
    assert hex_to_int("0xa1b") == 2587
