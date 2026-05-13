"""Shared output utilities — JSON serialization, Markdown rendering."""

from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any


class _EnumEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


def write_json(data: Any, path: str) -> None:
    """Write data to a JSON file, creating parent directories if needed."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    serializable = _to_serializable(data)
    out.write_text(json.dumps(serializable, indent=2, cls=_EnumEncoder, ensure_ascii=False))


def _to_serializable(obj: Any) -> Any:
    """Convert dataclasses and enums to plain dicts for JSON serialization."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_serializable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, list):
        return [_to_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    return obj


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print a simple Markdown-style table to stdout."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    header_line = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |"
    sep_line = "| " + " | ".join("-" * w for w in widths) + " |"

    print(header_line)
    print(sep_line)
    for row in rows:
        cells = [str(c).ljust(w) for c, w in zip(row, widths)]
        print("| " + " | ".join(cells) + " |")
