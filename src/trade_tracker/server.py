from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from web3 import Web3

from trade_tracker.config import EVENT_TOPIC_TYPE, Settings, apply_settings, load_settings
from trade_tracker.exporters.clickhouse import export_to_clickhouse, fetch_known_trade_keys
from trade_tracker.grouping import assign_groups
from trade_tracker.models import EventLog, Transaction
from trade_tracker.trades import create_trades


class RawContract(BaseModel):
    # Alchemy sends `address: null` and/or `decimals: null` for native ETH
    # transfers, so every field must be optional.
    raw_value: str | None = Field(None, alias="rawValue")
    address: str | None = None
    decimals: int | None = None


class LogEntry(BaseModel):
    address: str | None = None
    topics: list[str | None] = Field(default_factory=list)
    data: str | None = None
    block_number: str | None = Field(None, alias="blockNumber")
    transaction_hash: str | None = Field(None, alias="transactionHash")
    transaction_index: str | None = Field(None, alias="transactionIndex")
    block_hash: str | None = Field(None, alias="blockHash")
    log_index: str | None = Field(None, alias="logIndex")
    removed: bool = False


class Activity(BaseModel):
    block_num: str = Field(alias="blockNum")
    hash: str
    # `fromAddress`/`toAddress` can be null (contract creations, some internal transfers).
    from_address: str | None = Field(None, alias="fromAddress")
    to_address: str | None = Field(None, alias="toAddress")
    value: float | None = None
    erc721_token_id: str | None = Field(None, alias="erc721TokenId")
    # Alchemy sends a list of {tokenId, value} objects, not a dict.
    erc1155_metadata: list[dict] | None = Field(None, alias="erc1155Metadata")
    # `asset` is omitted when the token has no known symbol.
    asset: str | None = None
    category: str | None = None
    raw_contract: RawContract | None = Field(None, alias="rawContract")
    type_trace_address: str | None = Field(None, alias="typeTraceAddress")
    # External and internal ETH transfers have no event log.
    log: LogEntry | None = None


class Event(BaseModel):
    network: str | None = None
    activity: list[Activity] = Field(default_factory=list)


class WebhookPayload(BaseModel):
    webhook_id: str = Field(alias="webhookId")
    id: str
    # Alchemy has used both ISO strings and epoch-millisecond integers here.
    created_at: str | int = Field(alias="createdAt")
    type: str
    event: Event


app = FastAPI(title="Trade Tracker Webhook")


def _checksum_or_none(address: str | None) -> str | None:
    """Checksum an address, returning None when it is missing or malformed."""
    if not address:
        return None
    try:
        return Web3.to_checksum_address(address)
    except ValueError:
        logging.debug("Ignoring malformed address %r", address)
        return None


def _process_activity(settings: Settings, wallet_address: str, payload: WebhookPayload) -> dict:
    apply_settings(settings)
    checksum_wallet = Web3.to_checksum_address(wallet_address)

    tx_groups: dict[str, dict[str, Any]] = {}
    for act in payload.event.activity:
        from_addr = _checksum_or_none(act.from_address)
        to_addr = _checksum_or_none(act.to_address)
        if from_addr != checksum_wallet and to_addr != checksum_wallet:
            continue

        # External/internal ETH transfers (and other activity without an event
        # log) cannot produce trades; skip them instead of failing.
        if act.log is None:
            logging.debug("Skipping activity %s without event log (category=%s)", act.hash, act.category)
            continue

        topics = [t for t in act.log.topics if t]
        if not topics:
            logging.debug("Skipping activity %s without indexed topics", act.hash)
            continue

        topic0 = topics[0]
        event_type = EVENT_TOPIC_TYPE.get(topic0)
        if event_type is None:
            logging.debug("Unknown event topic %s", topic0)
            continue

        raw_contract = act.raw_contract
        raw_value = raw_contract.raw_value if raw_contract else None
        if not raw_value or raw_value == "0x":
            logging.debug("Skipping activity %s without raw transfer value", act.hash)
            continue
        amount = Web3.to_int(hexstr=raw_value)

        event_log = EventLog(
            token_address=(raw_contract.address or "") if raw_contract else "",
            sender="0x" + topics[1][-40:] if len(topics) > 1 else "",
            receiver="0x" + topics[2][-40:] if len(topics) > 2 else "",
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

    # Make retries idempotent: trades already stored must not be re-inserted
    # nor re-grouped (Alchemy retries any non-2xx delivery).
    if trades:
        known = fetch_known_trade_keys(
            settings.clickhouse_host,
            settings.clickhouse_port,
            settings.clickhouse_user,
            settings.clickhouse_password,
            settings.clickhouse_database,
        )
        trades = [t for t in trades if (t.transaction_hash, t.pair_name) not in known]

    if trades:
        assign_groups(
            trades,
            settings.clickhouse_host,
            settings.clickhouse_port,
            settings.clickhouse_user,
            settings.clickhouse_password,
            settings.clickhouse_database,
        )
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
async def wallet_activity(request: Request) -> dict:
    settings = load_settings()
    body = await request.body()

    if settings.webhook_signing_key:
        signature = request.headers.get("X-Alchemy-Signature", "")
        expected = hmac.new(
            settings.webhook_signing_key.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            logging.warning("Rejecting webhook delivery with invalid signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # The payload is parsed manually from the raw body instead of via a
    # FastAPI body parameter: a payload that does not match the model must be
    # acknowledged (2xx), never 4xx — Alchemy keeps retrying non-2xx
    # deliveries and disables webhooks that fail for 24 hours.
    try:
        payload = WebhookPayload.model_validate_json(body)
    except ValidationError as exc:
        logging.error("Ignoring malformed webhook payload: %s", exc)
        return {"status": "ok", "trades_created": 0, "message": "Malformed webhook payload ignored"}

    logging.debug("Webhook payload: %s", payload)

    wallet_address = settings.wallet_address
    if not wallet_address:
        raise HTTPException(status_code=500, detail="WALLET_ADDRESS not configured")

    try:
        result = await asyncio.to_thread(_process_activity, settings, wallet_address, payload)
    except Exception:
        # Transient failure (RPC/ClickHouse unreachable, ...): return 5xx so
        # Alchemy retries the delivery.
        logging.exception("Failed to process webhook event %s", payload.id)
        raise HTTPException(status_code=500, detail="Failed to process webhook event") from None
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

    # Fail fast on misconfiguration instead of failing every webhook delivery
    # for 24 hours until Alchemy disables the webhook.
    if not settings.wallet_address:
        raise SystemExit("WALLET_ADDRESS is not configured (env var, YAML config) — the webhook server cannot start")
    if not settings.alchemy_api_key:
        raise SystemExit("ALCHEMY_API_KEY is not configured (env var, YAML config) — the webhook server cannot start")
    try:
        Web3.to_checksum_address(settings.wallet_address)
    except ValueError as exc:
        raise SystemExit(f"WALLET_ADDRESS is not a valid address: {settings.wallet_address!r}") from exc

    uvicorn.run(
        "trade_tracker.server:app",
        host=settings.server_host,
        port=settings.server_port,
        log_level=settings.log_level.lower(),
    )
