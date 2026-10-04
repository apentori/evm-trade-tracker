from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from trade_tracker.config import Settings
from trade_tracker.server import WebhookPayload, app

WALLET = "0x503828976d22510aad0201ac7ec88293211d23da"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def _log(topics: list[str] | None = None) -> dict:
    if topics is None:
        topics = [
            TRANSFER_TOPIC,
            "0x000000000000000000000000503828976d22510aad0201ac7ec88293211d23da",
            "0x000000000000000000000000be3f4b43db5eb49d1f48f53443b9abce45da3b79",
        ]
    return {
        "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "topics": topics,
        "data": "0x0000000000000000000000000000000000000000000000000000000011783b21",
        "blockNumber": "0xdf34a3",
        "transactionHash": "0x7a4a39da2a3fa1fc2ef88fd1eaea070286ed2aba21e0419dcfb6d5c5d9f02a72",
        "transactionIndex": "0x46",
        "blockHash": "0xa99ec54413bd3db3f9bdb0c1ad3ab1400ee0ecefb47803e17f9d33bc4d0a1e91",
        "logIndex": "0x6e",
        "removed": False,
    }


def _activity(**overrides) -> dict:
    activity = {
        "blockNum": "0xdf34a3",
        "hash": "0x7a4a39da2a3fa1fc2ef88fd1eaea070286ed2aba21e0419dcfb6d5c5d9f02a72",
        "fromAddress": WALLET,
        "toAddress": "0xbe3f4b43db5eb49d1f48f53443b9abce45da3b79",
        "value": 293.092129,
        "erc721TokenId": None,
        "erc1155Metadata": None,
        "asset": "USDC",
        "category": "token",
        "rawContract": {
            "rawValue": "0x0000000000000000000000000000000000000000000000000000000011783b21",
            "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
            "decimals": 6,
        },
        "typeTraceAddress": None,
        "log": _log(),
    }
    activity.update(overrides)
    return {k: v for k, v in activity.items() if v is not None}


def _payload(activity: list[dict]) -> dict:
    return {
        "webhookId": "wh_k63lg72rxda78gce",
        "id": "whevt_vq499kv7elmlbp2v",
        "createdAt": "2024-01-23T07:42:26.411977228Z",
        "type": "ADDRESS_ACTIVITY",
        "event": {"network": "OPT_MAINNET", "activity": activity},
    }


def _settings(signing_key: str = "") -> Settings:
    return Settings(wallet_address=WALLET, webhook_signing_key=signing_key)


class TestWebhookPayloadModel:
    """Real Alchemy payloads that used to be rejected with a 422."""

    def test_erc20_token_transfer(self):
        WebhookPayload.model_validate(_payload([_activity()]))

    def test_external_eth_transfer(self):
        # Native ETH transfers have no event log and rawContract.address is null.
        WebhookPayload.model_validate(
            _payload(
                [
                    _activity(
                        value=1.5,
                        asset="ETH",
                        category="external",
                        rawContract={"rawValue": "0x14d1120d7b160000", "address": None, "decimals": 18},
                        typeTraceAddress=None,
                    )
                ]
            )
        )

    def test_internal_eth_transfer(self):
        WebhookPayload.model_validate(
            _payload(
                [
                    _activity(
                        value=0.5,
                        asset="ETH",
                        category="internal",
                        rawContract={"rawValue": "0x6f05b59d3b20000", "address": None, "decimals": 18},
                        typeTraceAddress="call_0_1",
                    )
                ]
            )
        )

    def test_erc1155_transfer(self):
        # erc1155Metadata is a list of {tokenId, value} objects and decimals can be null.
        WebhookPayload.model_validate(
            _payload(
                [
                    _activity(
                        value=None,
                        erc1155Metadata=[{"tokenId": "0x1", "value": "0x1"}],
                        asset="NFT",
                        category="erc1155",
                        rawContract={
                            "rawValue": "0x1",
                            "address": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
                            "decimals": None,
                        },
                    )
                ]
            )
        )

    def test_activity_without_asset(self):
        # Alchemy omits `asset` when the token has no known symbol.
        WebhookPayload.model_validate(_payload([_activity(value=None, asset=None)]))

    def test_epoch_millisecond_created_at(self):
        payload = _payload([_activity()])
        payload["createdAt"] = 1701388800000
        WebhookPayload.model_validate(payload)

    def test_log_with_empty_topics(self):
        WebhookPayload.model_validate(_payload([_activity(log=_log(topics=[]))]))


class TestWebhookEndpoint:
    def test_valid_payload_returns_200(self):
        def fake_process(settings, wallet, payload):
            return {"status": "ok", "trades_created": 0}

        with (
            patch("trade_tracker.server.load_settings", return_value=_settings()),
            patch("trade_tracker.server._process_activity", side_effect=fake_process) as mock_process,
        ):
            with TestClient(app) as client:
                response = client.post("/wallet_activity", json=_payload([_activity()]))
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_process.assert_called_once()

    def test_malformed_payload_returns_200(self):
        # Malformed payloads must be acknowledged (2xx): Alchemy retries any
        # non-2xx delivery forever and disables webhooks after 24h of failures.
        with patch("trade_tracker.server.load_settings", return_value=_settings()):
            with TestClient(app) as client:
                response = client.post("/wallet_activity", json={"totally": "unexpected"})
        assert response.status_code == 200
        assert response.json()["message"] == "Malformed webhook payload ignored"

    def test_invalid_signature_returns_401(self):
        signing_key = "whsec_test"
        with patch("trade_tracker.server.load_settings", return_value=_settings(signing_key)):
            with TestClient(app) as client:
                response = client.post("/wallet_activity", json=_payload([_activity()]))
        assert response.status_code == 401

    def test_valid_signature_returns_200(self):
        signing_key = "whsec_test"

        def sign(body: bytes) -> str:
            return hmac.new(signing_key.encode(), body, hashlib.sha256).hexdigest()

        def fake_process(settings, wallet, payload):
            return {"status": "ok", "trades_created": 0}

        with (
            patch("trade_tracker.server.load_settings", return_value=_settings(signing_key)),
            patch("trade_tracker.server._process_activity", side_effect=fake_process),
        ):
            with TestClient(app) as client:
                body = json.dumps(_payload([_activity()])).encode()
                response = client.post(
                    "/wallet_activity",
                    content=body,
                    headers={"Content-Type": "application/json", "X-Alchemy-Signature": sign(body)},
                )
        assert response.status_code == 200

    def test_processing_failure_returns_500(self):
        # Transient processing failures (RPC/ClickHouse down) return 5xx so
        # Alchemy retries the delivery.
        with (
            patch("trade_tracker.server.load_settings", return_value=_settings()),
            patch("trade_tracker.server._process_activity", side_effect=RuntimeError("clickhouse down")),
        ):
            with TestClient(app) as client:
                response = client.post("/wallet_activity", json=_payload([_activity()]))
        assert response.status_code == 500

    def test_activity_without_log_is_skipped_not_crashing(self):
        # _process_activity must skip activities without an event log instead of
        # raising on act.log.topics.
        with patch("trade_tracker.server.load_settings", return_value=_settings()):
            with TestClient(app) as client:
                response = client.post(
                    "/wallet_activity",
                    json=_payload([_activity(value=None, asset=None, log=None, category="external", rawContract=None)]),
                )
        assert response.status_code == 200
        assert response.json()["trades_created"] == 0

    def test_activity_with_malformed_address_is_skipped(self):
        # Payload content must never cause a 500: Alchemy retries non-2xx
        # deliveries and disables webhooks that keep failing.
        with patch("trade_tracker.server.load_settings", return_value=_settings()):
            with TestClient(app) as client:
                response = client.post(
                    "/wallet_activity",
                    json=_payload([_activity(fromAddress="not-an-address", toAddress="also-not-an-address")]),
                )
        assert response.status_code == 200
        assert response.json()["trades_created"] == 0
