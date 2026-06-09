from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class EventLog:
    token_address: str
    sender: str
    receiver: str
    amount: int
    event_type: str


@dataclass
class Transaction:
    hash: str
    from_address: str
    to_address: str
    value: int
    block: int
    event_logs: list[EventLog]
    timestamp: int = 0

    def add_event_log(self, event: EventLog) -> None:
        self.event_logs.append(event)


@dataclass
class Trade:
    transaction_hash: str
    trade_timestamp: int
    block_number: int
    pair_name: str
    base_token: str
    quote_token: str
    amount_base: float
    amount_quote: float
    price: float
    type: str
    sender: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
