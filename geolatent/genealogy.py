"""
geolatent/genealogy.py
Immortal cell fossil tracking — FIFO ledger with 2000-entry cap.

A spatial cell is declared Immortal when its persistence score reaches
>= 0.5 × FIFO_CAP (i.e. ≥ 1000 consecutive stable ticks).
"""
from __future__ import annotations

import math
from collections import OrderedDict
from typing import List

_FIFO_CAP  = 2000
_THRESHOLD = 0.5   # fraction of FIFO_CAP → 1000 ticks to qualify


def update_immortal_candidates(state, terrain, sigma_band: float = 1.0) -> None:
    """
    For each terrain cell within [μ − σ·band, μ + σ·band], increment its
    persistence tick count. Cells outside the band are evicted.
    Enforces a FIFO cap of 2000 entries (oldest-first eviction).
    """
    if not terrain:
        return
    rows = len(terrain)
    cols = len(terrain[0]) if rows else 0
    if rows == 0 or cols == 0:
        return

    flat: list = []
    for row in terrain:
        for v in (row if isinstance(row, list) else row.tolist()):
            flat.append(float(v))
    if not flat:
        return

    mu    = sum(flat) / len(flat)
    sigma = math.sqrt(sum((v - mu) ** 2 for v in flat) / len(flat)) or 1.0
    lo, hi = mu - sigma_band * sigma, mu + sigma_band * sigma

    # Migrate plain dict → OrderedDict on first call (WorldState starts with dict)
    if not isinstance(state.immortal_candidates, OrderedDict):
        state.immortal_candidates = OrderedDict(state.immortal_candidates)

    cands = state.immortal_candidates
    for gy in range(rows):
        for gx in range(cols):
            v   = terrain[gy][gx] if isinstance(terrain[gy], list) else float(terrain[gy][gx])
            key = (gx, gy)
            if lo <= v <= hi:
                if key in cands:
                    cands.move_to_end(key)
                    cands[key] = min(_FIFO_CAP, cands[key] + 1)
                else:
                    cands[key] = 1
                    # FIFO eviction: remove oldest entry if over cap
                    while len(cands) > _FIFO_CAP:
                        cands.popitem(last=False)
            else:
                cands.pop(key, None)


def get_immortal_cells(state, threshold: float = _THRESHOLD) -> List[dict]:
    """
    Return cells whose tick count >= threshold × FIFO_CAP.
    Default: threshold=0.5 → must be stable for ≥ 1000 ticks.
    """
    min_ticks = int(threshold * _FIFO_CAP)
    return [
        {"gx": k[0], "gy": k[1], "ticks": v}
        for k, v in state.immortal_candidates.items()
        if v >= min_ticks
    ]


# Legacy alias used by simulator.py callers
def get_immortal_cells_local(state, threshold: int = 2000) -> List[dict]:
    """Backward-compatible alias. threshold is a raw tick count."""
    return [
        {"gx": k[0], "gy": k[1], "ticks": v}
        for k, v in state.immortal_candidates.items()
        if v >= threshold
    ]
