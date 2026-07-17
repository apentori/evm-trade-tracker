from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from web3 import Web3

from trade_tracker.config import EVENT_TOPIC_TYPE, Settings, apply_settings, load_settings
from trade_tracker.exporters.clickhouse import export_to_clickhouse
from trade_tracker.models import EventLog, Transaction
from trade_tracker.trades import create_trades


class RawContract(BaseModel):
    raw_value: str = Field(alias="rawValue")
    address: str
    decimals: int


class LogEntry(BaseModel):
    address: str
    topics: list[str]
    data: str
    block_number: str = Field(alias="blockNumber")
    transaction_hash: str = Field(alias="transactionHash")
    transaction_index: str = Field(alias="transactionIndex")
    block_hash: str = Field(alias="blockHash")
    log_index: str = Field(alias="logIndex")
    removed: bool


class Activity(BaseModel):
    block_num: str = Field(alias="blockNum")
    hash: str
    from_address: str = Field(alias="fromAddress")
    to_address: str = Field(alias="toAddress")
    value: float | None = None
    erc721_token_id: str | None = Field(None, alias="erc721TokenId")
    erc1155_metadata: dict | None = Field(None, alias="erc1155Metadata")
    asset: str
    category: str
    raw_contract: RawContract = Field(alias="rawContract")
    type_trace_address: str | None = Field(None, alias="typeTraceAddress")
    log: LogEntry


class Event(BaseModel):
    network: str
    activity: list[Activity]


class WebhookPayload(BaseModel):
    webhook_id: str = Field(alias="webhookId")
    id: str
    created_at: str = Field(alias="createdAt")
    type: str
    event: Event


app = FastAPI(title="Trade Tracker Webhook")


def _process_activity(settings: Settings, wallet_address: str, payload: WebhookPayload) -> dict:
    apply_settings(settings)
    checksum_wallet = Web3.to_checksum_address(wallet_address)

    tx_groups: dict[str, dict[str, Any]] = {}
    for act in payload.event.activity:
        from_addr = Web3.to_checksum_address(act.from_address)
        to_addr = Web3.to_checksum_address(act.to_address)
        if from_addr != checksum_wallet and to_addr != checksum_wallet:
            continue

        topic0 = act.log.topics[0]
        event_type = EVENT_TOPIC_TYPE.get(topic0)
        if event_type is None:
            logging.debug("Unknown event topic %s", topic0)
            continue

        amount = Web3.to_int(hexstr=act.raw_contract.raw_value)

        event_log = EventLog(
            token_address=act.raw_contract.address,
            sender="0x" + act.log.topics[1][-40:] if len(act.log.topics) > 1 else "",
            receiver="0x" + act.log.topics[2][-40:] if len(act.log.topics) > 2 else "",
            amount=amount,
            event_type=event_type,
        )

        tx_hash = act.hash
        if tx_hash not in tx_groups:
            tx_groups[tx_hash] = {
                "block_num": int(act.block_num, 16),
                "from_address": act.from_address,
                "to_address": act.to_address,
                "event_logs": [],
            }
        tx_groups[tx_hash]["event_logs"].append(event_log)

    if not tx_groups:
        return {"status": "ok", "trades_created": 0, "message": "No matching activity for configured wallet"}

    rpc_url = f"{settings.alchemy_url}/{settings.alchemy_api_key}"
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    transactions: list[Transaction] = []
    for tx_hash, group in tx_groups.items():
        block = w3.eth.get_block(group["block_num"])
        timestamp = block.get("timestamp", 0)
        transactions.append(
            Transaction(
                hash=tx_hash,
                from_address=group["from_address"],
                to_address=group["to_address"],
                value=0,
                block=group["block_num"],
                event_logs=group["event_logs"],
                timestamp=timestamp,
            )
        )

    trades = create_trades(w3, [transactions], wallet_address, pairs=list(settings.pairs))

    if trades:
        export_to_clickhouse(
            trades,
            settings.clickhouse_host,
            settings.clickhouse_port,
            settings.clickhouse_user,
            settings.clickhouse_password,
            settings.clickhouse_database,
            settings.clickhouse_table,
        )

    return {"status": "ok", "trades_created": len(trades)}


@app.post("/wallet_activity")
async def wallet_activity(request: Request, payload: WebhookPayload) -> dict:
    settings = load_settings()

    if settings.webhook_signing_key:
        body = await request.body()
        signature = request.headers.get("X-Alchemy-Signature", "")
        expected = hmac.new(
            settings.webhook_signing_key.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    wallet_address = settings.wallet_address
    if not wallet_address:
        raise HTTPException(status_code=500, detail="WALLET_ADDRESS not configured")
    logging.info(f"Payload {payload}")
    result = await asyncio.to_thread(_process_activity, settings, wallet_address, payload)
    return result


def run() -> None:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(prog="trade-tracker-server")
    parser.add_argument("--config", type=str, default=None, help="Path to YAML config file")
    args = parser.parse_args()

    settings = load_settings(args.config)
    apply_settings(settings)
    logging.basicConfig(level=str(settings.log_level).upper())

    uvicorn.run(
        "trade_tracker.server:app",
        host=settings.server_host,
        port=settings.server_port,
        log_level=settings.log_level.lower(),
    )
