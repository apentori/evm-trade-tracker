from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from web3 import Web3


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

    @property
    def value_eth(self) -> float:
        return float(Web3.from_wei(self.value, "ether"))

    def add_event_log(self, event: EventLog) -> None:
        self.event_logs.append(event)


@dataclass
class Trade:
    transaction_hash: str
    trade_timestamp: int
    block_number: int
    amount_eth: float
    amount_usdc: float
    eth_sender: str
    eth_receiver: str
    token: str
    token_address: str
    token_sender: str
    token_receiver: str
    price: float
    type: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
