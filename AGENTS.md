# Trade Tracker – Developer Notes

## Commands

```bash
# Install the package in editable mode
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=src/trade_tracker

# Lint check
ruff check src/tests

# Format
ruff format src tests

# Run the CLI
trade-tracker -w <WALLET> -k <API_KEY>

# Run as module
python -m trade_tracker -w <WALLET> -k <API_KEY>
```

## Structure

```
src/trade_tracker/
├── __init__.py
├── __main__.py          # python -m entry point
├── cli.py               # Click CLI
├── config.py            # Settings & constants
├── models.py            # Dataclasses
├── cache.py             # Token metadata cache
├── alchemy.py           # Alchemy API client
├── blockchain.py        # Web3 interaction, event parsing
├── trades.py            # Trade creation logic
└── exporters/
    ├── __init__.py
    ├── json_exporter.py
    └── clickhouse.py
```
