"""
geolatent/adapters.py
Dataset adapters: CSV / JSONL → DataPoint translation.

CSV schema (normalised [0, 1]):
  x, y              — spatial coordinates (required)
  energy            — magnitude (optional, default 1.0)
  kind              — neutral | prey | predator (optional, default neutral)
  variance_score    — volatility (optional)
  entity_id         — identifier (optional, ignored by engine)
  timestamp         — tick (optional, ignored by engine for now)
  payload_value     — alias for energy (from ingestion API schema)

JSONL schema: one JSON object per line, same fields as CSV.

Prototype pollution guard: __proto__, constructor, prototype keys are stripped.
"""
from __future__ import annotations

import csv
import io
import json
import math
from typing import Iterator, List

from geolatent.simulator import DataPoint

_BLOCKED_KEYS = {"__proto__", "constructor", "prototype"}


def _sanitise(d: dict) -> dict:
    """Strip prototype-pollution keys from an incoming dict."""
    return {k: v for k, v in d.items() if k not in _BLOCKED_KEYS}


def _normalise(val: float, lo: float, hi: float) -> float:
    """Normalise val from [lo, hi] to [0, 1], clamp to [0, 1]."""
    if hi == lo:
        return 0.5
    return max(0.0, min(1.0, (val - lo) / (hi - lo)))


def _to_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _row_to_datapoint(row: dict) -> DataPoint:
    row = _sanitise(row)
    energy = _to_float(row.get("energy") or row.get("payload_value"), 1.0)
    return DataPoint(
        x=_to_float(row.get("x"), 0.5),
        y=_to_float(row.get("y"), 0.5),
        energy=max(0.01, energy),
        kind=str(row.get("kind", "neutral")).lower(),
        variance=_to_float(row.get("variance_score") or row.get("variance"), 0.0),
    )


def _auto_normalise(points: list[DataPoint]) -> list[DataPoint]:
    """
    Auto-normalise x/y to [0, 1] if values appear to be outside that range.
    """
    xs = [p.x for p in points]
    ys = [p.y for p in points]
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    if x_hi > 1.0 or x_lo < 0.0 or y_hi > 1.0 or y_lo < 0.0:
        for p in points:
            p.x = _normalise(p.x, x_lo, x_hi)
            p.y = _normalise(p.y, y_lo, y_hi)
    return points


def from_csv_bytes(content: bytes) -> list[DataPoint]:
    """Parse CSV bytes into a list of DataPoints."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    points = [_row_to_datapoint(row) for row in reader]
    return _auto_normalise(points)


def from_jsonl_bytes(content: bytes) -> list[DataPoint]:
    """Parse JSONL bytes into a list of DataPoints."""
    points = []
    for line in content.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            points.append(_row_to_datapoint(obj))
    return _auto_normalise(points)


def from_file(path: str) -> list[DataPoint]:
    """Auto-detect CSV or JSONL from file extension."""
    with open(path, "rb") as f:
        content = f.read()
    if path.lower().endswith(".jsonl"):
        return from_jsonl_bytes(content)
    return from_csv_bytes(content)


def iter_batches(points: list[DataPoint], batch_size: int = 20) -> Iterator[list[DataPoint]]:
    """Yield points in batches for streaming inflow."""
    for i in range(0, len(points), batch_size):
        yield points[i:i + batch_size]
