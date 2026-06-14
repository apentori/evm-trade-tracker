from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from trade_tracker.models import Trade


class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def export_to_json(trades: Sequence[Trade], path: str = "trades.json") -> None:
    dict_data = [t.to_dict() for t in trades]
    Path(path).write_text(json.dumps(dict_data, indent=4, cls=DateTimeEncoder), encoding="utf-8")
    print(f"Exported {len(dict_data)} trades to {path}")
