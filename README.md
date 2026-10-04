# Trade Tracker

Track token trades on EVM networks (Optimism, Ethereum, Arbitrum, etc.).

Uses the Alchemy API to find blocks containing wallet activity, then Web3 to
fetch transaction details and event logs, and creates structured Trade records
exportable to JSON or ClickHouse.

## Quick Start

```bash
pip install -e .
trade-tracker -w <WALLET> -k <API_KEY> --to-json
```

## Configuration

Configuration is resolved in this order (highest priority wins):

**CLI flags > environment variables > YAML file > code defaults**

### YAML file

Auto-discovered from these paths (first found wins):

1. `--config <path>` flag
2. `$XDG_CONFIG_HOME/trade-tracker/config.yaml`
3. `~/.config/trade-tracker/config.yaml`
4. `./trade-tracker.yaml`

```yaml
# trade-tracker.yaml
alchemy:
  url: "https://opt-mainnet.g.alchemy.com/v2"
  api_key: ""

wallet_address: "0x..."

pairs:
  - name: "ETH/USDC"
    base_token: "0x4200000000000000000000000000000000000006"
    quote_token: "0x0b2c639c533813f4aa9d7837caf62653d097ff85"
    base_decimals: 18
    quote_decimals: 6

events:
  topic_types:
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef": "TRANSFER"

clickhouse:
  host: "localhost"
  port: 9000
  database: "default"
  table: "trades"

log_level: "INFO"
```

### Environment variables

Any YAML key can be overridden with an env var:

```bash
export ALCHEMY_API_KEY="your-key"
export WALLET_ADDRESS="0x..."
export CLICKHOUSE_PORT=8123
trade-tracker
```

### Multi-network

Change the RPC URL and token addresses per network:

```yaml
# Arbitrum
alchemy:
  url: "https://arb-mainnet.g.alchemy.com/v2"

pairs:
  - name: "ETH/USDC"
    base_token: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1"
    quote_token: "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
    base_decimals: 18
    quote_decimals: 6
```

## Trade Pairs

A **pair** defines what constitutes a trade:

- `base_token` — the asset being bought or sold (e.g. WETH)
- `quote_token` — the asset used as payment (e.g. USDC)
- `base_decimals` / `quote_decimals` — token decimal places

The wallet must move **both** tokens in a transaction for a trade to be recorded.

| Wallet sends | Wallet receives | Trade type |
|---|---|---|
| quote token | base token | **BUY** |
| base token | quote token | **SELL** |

Multiple pairs can be defined — each matching pair in a transaction produces a
separate Trade record.

## Usage

```bash
# Single scan
trade-tracker -w 0x... -k KEY

# Scan from a specific block range
trade-tracker -w 0x... -k KEY --from-block 10000000 --to-block 10000100

# Export to JSON
trade-tracker -w 0x... -k KEY --to-json

# Follow mode: continues from last stored block (requires ClickHouse)
trade-tracker -w 0x... -k KEY --follow

# Full scan (scan every block instead of using Alchemy API)
trade-tracker -w 0x... -k KEY --full
```

Re-scans are idempotent: trades already stored in ClickHouse are skipped, so
overlapping `--from-block`/`--to-block` ranges never duplicate trades or
groups.

## Webhook server

Instead of polling, run the FastAPI server to receive real-time Address
Activity webhooks from Alchemy:

```bash
trade-tracker-server --config /path/to/trade-tracker.yaml
```

- Endpoint: `POST /wallet_activity` — configure your Alchemy webhook URL as
  `https://your-host:8000/wallet_activity`.
- Set `WALLET_ADDRESS` and `ALCHEMY_API_KEY` (env vars or YAML config).
- To verify deliveries, set `webhook.signing_key` in the YAML config (or
  `WEBHOOK_SIGNING_KEY`) to the **per-webhook signing key** from the Alchemy
  dashboard; requests with a bad signature are rejected with 401.
- Malformed payloads are acknowledged with a 2xx (logged and ignored) —
  Alchemy retries any non-2xx delivery and disables webhooks that keep
  failing for 24 hours. Transient processing failures (RPC/ClickHouse
  unreachable) return 5xx so Alchemy retries them.
- Deliveries are processed idempotently: retried events never duplicate
  trades or groups.

## ClickHouse schema

`trades` and `trades_group` use `ReplacingMergeTree(version)` ordered by
`(transaction_hash, pair_name, trade_datetime)`; `trades_group` rows carry a
`version` so a trade's `close` row deterministically replaces its `open` row.
See [docs/clickhouse-migration.md](docs/clickhouse-migration.md) to migrate
existing tables.

## Nix / NixOS

```bash
nix develop          # enter shell with trade-tracker in PATH
trade-tracker --help

# Or run directly
nix run
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```
