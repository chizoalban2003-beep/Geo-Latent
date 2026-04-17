"""
geolatent/persistence.py
File-backed snapshot write/read and replay support.
"""
from __future__ import annotations
import json, os, pathlib
from typing import Iterator


def save_snapshot(data: dict, directory: str, step: int) -> str:
    pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
    path = os.path.join(directory, f"frame_{step:06d}.json")
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def load_snapshot(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def iter_replay(directory: str, start: int = 0, limit: int | None = None) -> Iterator[dict]:
    p = pathlib.Path(directory)
    files = sorted(p.glob("frame_*.json"))
    if start:
        files = [f for f in files if int(f.stem.split("_")[1]) >= start]
    if limit:
        files = files[:limit]
    for f in files:
        yield load_snapshot(str(f))
