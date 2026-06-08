from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from trade_tracker.models import Trade


def export_to_json(trades: Sequence[Trade], path: str = "trades.json") -> None:
    dict_data = [t.to_dict() for t in trades]
    Path(path).write_text(json.dumps(dict_data, indent=4), encoding="utf-8")
    print(f"Exported {len(dict_data)} trades to {path}")
