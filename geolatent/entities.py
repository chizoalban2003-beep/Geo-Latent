"""
geolatent/entities.py
In-world artifact synthesis: fossils, mist particles, beacons.
"""
from __future__ import annotations
import math, random
from geolatent.simulator import WorldState


def synthesise_entities(state: WorldState) -> list[dict]:
    """Return a list of entity dicts for the current state."""
    entities: list[dict] = []
    entities.extend(_fossils(state))
    entities.extend(_mist(state))
    entities.extend(_beacons(state))
    return entities


def _fossils(state: WorldState) -> list[dict]:
    result = []
    for (gx, gy), ticks in state.immortal_candidates.items():
        if ticks >= 500:
            result.append({
                "type":  "fossil",
                "gx":    gx, "gy": gy,
                "ticks": ticks,
                "label": f"Fossil ({gx},{gy})",
                "immortal": ticks >= 2000,
            })
    return result[:50]  # cap render count


def _mist(state: WorldState) -> list[dict]:
    return [
        {"type": "mist", "x": round(p.x, 4), "y": round(p.y, 4),
         "energy": round(p.energy, 3)}
        for p in state.atmosphere[:30]
    ]


def _beacons(state: WorldState) -> list[dict]:
    """High-energy predator clusters become glowing beacons."""
    beacons = []
    for pt in state.active:
        if pt.kind == "predator" and pt.energy > 3.0:
            beacons.append({
                "type":   "beacon",
                "x":      round(pt.x, 4),
                "y":      round(pt.y, 4),
                "energy": round(pt.energy, 3),
                "label":  "Predator beacon",
            })
    return beacons[:20]
