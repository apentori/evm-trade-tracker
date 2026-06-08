# Trade Tracker

Track trades on the Optimism network.

Uses the Alchemy API to find blocks containing wallet activity, then Web3 to
fetch transaction details and event logs, and creates structured Trade records
exportable to JSON or ClickHouse.

## Quick Start

```bash
pip install -e .
trade-tracker -w <WALLET> -k <API_KEY> --to-json
```

