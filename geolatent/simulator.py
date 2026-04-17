"""
geolatent/simulator.py
World physics and terrain synthesis.

KEY FIX: synthesize_topology() is now O(N·σ²) using numpy broadcasting
         instead of the previous O(W·H·N) pure-Python nested loop.
         ~10–100× faster at default settings (40×24 grid, σ=2.8).
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DataPoint:
    x: float               # normalised [0, 1]
    y: float               # normalised [0, 1]
    energy: float = 1.0    # magnitude (payload_value)
    kind: str = "neutral"  # neutral | prey | predator
    age: int = 0
    variance: float = 0.0  # volatility score


@dataclass
class WorldState:
    grid_w: int = 40
    grid_h: int = 24
    active: List[DataPoint] = field(default_factory=list)
    abyss:  List[DataPoint] = field(default_factory=list)   # submerged / stale
    atmosphere: List[DataPoint] = field(default_factory=list)  # evaporated / mist
    terrain: object = None    # numpy array or list-of-lists
    sea_level: float = 0.15
    step: int = 0
    sigma: float = 2.8
    temperature: float = 1.0   # "melting" factor
    carrying_capacity: float = 500.0
    total_energy: float = 0.0
    biome_map: dict = field(default_factory=dict)  # (gx, gy) → label
    immortal_candidates: dict = field(default_factory=dict)  # (gx, gy) → tick count


# ---------------------------------------------------------------------------
# Numpy-vectorized KDE  (THE KEY FIX)
# ---------------------------------------------------------------------------

def synthesize_topology_numpy(state: WorldState):
    """
    Multivariate KDE terrain synthesis using numpy broadcasting.
    O(N · σ²) — only updates cells within ceil(3σ) of each point.
    """
    W, H = state.grid_w, state.grid_h
    sigma = state.sigma
    terrain = np.zeros((H, W), dtype=np.float32)

    if not state.active:
        return terrain

    cutoff = int(math.ceil(3 * sigma))
    gx_all = np.arange(W, dtype=np.float32)
    gy_all = np.arange(H, dtype=np.float32)
    norm_factor = 1.0 / (2.0 * math.pi * sigma * sigma)

    for pt in state.active:
        px = pt.x * W
        py = pt.y * H
        energy = max(0.0, pt.energy)

        x_lo = max(0, int(px) - cutoff)
        x_hi = min(W, int(px) + cutoff + 1)
        y_lo = max(0, int(py) - cutoff)
        y_hi = min(H, int(py) + cutoff + 1)

        cx = gx_all[x_lo:x_hi]
        cy = gy_all[y_lo:y_hi]
        CX, CY = np.meshgrid(cx, cy)

        dx = (CX - px) / sigma
        dy = (CY - py) / sigma
        kernel = norm_factor * np.exp(-0.5 * (dx * dx + dy * dy))
        terrain[y_lo:y_hi, x_lo:x_hi] += (kernel * energy).astype(np.float32)

    return terrain


def synthesize_topology_python(state: WorldState):
    """Pure-Python fallback when numpy is not available."""
    W, H = state.grid_w, state.grid_h
    sigma = state.sigma
    terrain = [[0.0] * W for _ in range(H)]
    norm = 1.0 / (2.0 * math.pi * sigma * sigma)
    cutoff = int(math.ceil(3 * sigma))

    for pt in state.active:
        px = pt.x * W
        py = pt.y * H
        x_lo = max(0, int(px) - cutoff)
        x_hi = min(W, int(px) + cutoff + 1)
        y_lo = max(0, int(py) - cutoff)
        y_hi = min(H, int(py) + cutoff + 1)
        for gy in range(y_lo, y_hi):
            for gx in range(x_lo, x_hi):
                dx = (gx - px) / sigma
                dy = (gy - py) / sigma
                terrain[gy][gx] += norm * math.exp(-0.5 * (dx * dx + dy * dy)) * pt.energy

    return terrain


def synthesize_topology(state: WorldState):
    """Dispatch to numpy or pure-Python implementation."""
    if _HAS_NUMPY:
        arr = synthesize_topology_numpy(state)
        return arr.tolist()
    return synthesize_topology_python(state)


# ---------------------------------------------------------------------------
# Biome labeling  (hybrid scientific + poetic naming)
# ---------------------------------------------------------------------------

_BIOME_TABLE = [
    # (variance_thresh, gradient_thresh, poetic_name, stat_name)
    (0.05, 0.05, "The Whispering Shelf",    "Low-Variance Plateau"),
    (0.20, 0.10, "The Tidal Archive",       "Seasonal Density Basin"),
    (0.15, 0.35, "The Fracture Bloom",      "High-Gradient Drift Zone"),
    (0.40, 0.20, "The Crown of Noise",      "High-Variance Highlands"),
    (0.10, 0.50, "The Null Fens",           "Sparse Anomaly Wetland"),
    (0.60, 0.60, "The Shattering Meridian", "Extreme Instability Ridge"),
    (0.05, 0.80, "The Deep Trench",         "Abyssal Low-Density Canyon"),
    (0.30, 0.15, "The Amber Steppe",        "Mid-Variance Transition Belt"),
]


def label_biome(local_variance: float, local_gradient: float) -> str:
    best = ("The Uncharted Expanse", "Undefined Region")
    best_dist = float("inf")
    for v_thresh, g_thresh, poetic, stat in _BIOME_TABLE:
        dist = math.hypot(local_variance - v_thresh, local_gradient - g_thresh)
        if dist < best_dist:
            best_dist = dist
            best = (poetic, stat)
    return f"{best[0]} — {best[1]}"


def compute_biome_map(terrain, grid_w: int, grid_h: int) -> dict:
    """
    Compute a biome label for each cell using local variance and gradient.
    Returns dict of (gx, gy) → label string.
    """
    biomes: dict = {}
    rows = len(terrain)
    cols = len(terrain[0]) if rows else 0

    def _val(r, c):
        r = max(0, min(rows - 1, r))
        c = max(0, min(cols - 1, c))
        return terrain[r][c] if isinstance(terrain[r], list) else float(terrain[r][c])

    for gy in range(rows):
        for gx in range(cols):
            # Local variance from 3×3 neighbourhood
            neighbours = [_val(gy + dr, gx + dc)
                          for dr in (-1, 0, 1) for dc in (-1, 0, 1)]
            mu = sum(neighbours) / 9
            var = math.sqrt(sum((v - mu) ** 2 for v in neighbours) / 9)
            # Local gradient (Sobel-ish)
            grad = math.hypot(
                _val(gy, gx + 1) - _val(gy, gx - 1),
                _val(gy + 1, gx) - _val(gy - 1, gx),
            )
            biomes[(gx, gy)] = label_biome(var, grad)

    return biomes


# ---------------------------------------------------------------------------
# Predator–Prey terrain erosion  (Lotka–Volterra inspired)
# ---------------------------------------------------------------------------

def apply_lotka_volterra(state: WorldState, alpha=1.1, beta=0.4,
                          delta=0.1, gamma=0.4, dt=0.05) -> None:
    """
    Modifies point energies in-place to simulate competitive terrain erosion.
    prey: dx/dt  = alpha*x  - beta*x*y
    pred: dy/dt  = delta*x*y - gamma*y
    """
    prey  = [p for p in state.active if p.kind == "prey"]
    pred  = [p for p in state.active if p.kind == "predator"]

    x = sum(p.energy for p in prey)  / max(1, len(prey))
    y = sum(p.energy for p in pred)  / max(1, len(pred))

    dx = (alpha * x - beta  * x * y) * dt
    dy = (delta * x * y - gamma * y) * dt

    for p in prey:
        p.energy = max(0.01, p.energy + dx)
    for p in pred:
        p.energy = max(0.01, p.energy + dy)


# ---------------------------------------------------------------------------
# Water cycle  (data lifecycle)
# ---------------------------------------------------------------------------

def precipitation(state: WorldState, new_points: List[DataPoint]) -> None:
    """New records arrive as Data Rain — re-energise and enter active pool."""
    for pt in new_points:
        pt.age = 0
        state.active.append(pt)


def liquefaction(state: WorldState, stale_threshold: int = 80) -> None:
    """Stale records lose elevation and sink below sea level → abyss."""
    still_active = []
    for pt in state.active:
        pt.age += 1
        if pt.age > stale_threshold:
            state.abyss.append(pt)
        else:
            still_active.append(pt)
    state.active = still_active


def abyss_mutation(state: WorldState, mutation_rate: float = 0.05) -> None:
    """Submerged records undergo stochastic drift and recombination."""
    for pt in state.abyss:
        if random.random() < mutation_rate:
            pt.x = max(0.0, min(1.0, pt.x + random.gauss(0, 0.05)))
            pt.y = max(0.0, min(1.0, pt.y + random.gauss(0, 0.05)))
            pt.energy *= random.uniform(0.85, 1.15)
            pt.variance = abs(random.gauss(0, 0.1))


def evaporation(state: WorldState, evap_rate: float = 0.02) -> None:
    """Mutants evaporate from abyss → atmosphere (latent context)."""
    survivors = []
    for pt in state.abyss:
        if random.random() < evap_rate:
            state.atmosphere.append(pt)
        else:
            survivors.append(pt)
    state.abyss = survivors


def condensation(state: WorldState, condense_rate: float = 0.01) -> None:
    """Atmospheric mutants re-condense into new active precipitation."""
    survivors = []
    for pt in state.atmosphere:
        if random.random() < condense_rate:
            pt.age = 0
            state.active.append(pt)
        else:
            survivors.append(pt)
    state.atmosphere = survivors


# ---------------------------------------------------------------------------
# Carrying-capacity sea rise
# ---------------------------------------------------------------------------

def apply_carrying_capacity(state: WorldState) -> None:
    """
    Zero-sum energy economy + sea-level homeostasis.
    When active pool exceeds carrying capacity, sea rises.
    Boosting one peak draws energy from elsewhere.
    """
    n = len(state.active)
    if n == 0:
        return

    total = sum(p.energy for p in state.active)
    state.total_energy = total

    # Normalise to conserve total energy (zero-sum)
    if total > 0:
        target = state.total_energy / n
        for pt in state.active:
            pt.energy = pt.energy * 0.95 + target * 0.05

    # Sea rises with overload
    overload = max(0.0, n - state.carrying_capacity) / state.carrying_capacity
    state.sea_level = min(0.9, state.sea_level + overload * 0.01)
    state.sea_level = max(0.0, state.sea_level - 0.001)   # slow natural drain


# ---------------------------------------------------------------------------
# Immortal cell detection (Fossil Tracking)
# ---------------------------------------------------------------------------

def update_immortal_candidates(state: WorldState, terrain, sigma_band: float = 1.0) -> None:
    """
    If a cell stays within 1σ density range for 2000 consecutive ticks,
    it is etched as an Immortal Cell.
    """
    if not terrain:
        return

    rows = len(terrain)
    cols = len(terrain[0]) if rows else 0
    if rows == 0 or cols == 0:
        return

    # Flatten for stats
    flat = []
    for row in terrain:
        for v in (row if isinstance(row, list) else row.tolist()):
            flat.append(v)
    if not flat:
        return

    mu = sum(flat) / len(flat)
    sigma = math.sqrt(sum((v - mu) ** 2 for v in flat) / len(flat)) or 1.0
    lo, hi = mu - sigma_band * sigma, mu + sigma_band * sigma

    for gy in range(rows):
        for gx in range(cols):
            v = terrain[gy][gx] if isinstance(terrain[gy], list) else float(terrain[gy][gx])
            key = (gx, gy)
            if lo <= v <= hi:
                state.immortal_candidates[key] = state.immortal_candidates.get(key, 0) + 1
            else:
                state.immortal_candidates.pop(key, None)


def get_immortal_cells_local(state: WorldState, threshold: int = 2000) -> list:
    return [{"gx": k[0], "gy": k[1], "ticks": v}
            for k, v in state.immortal_candidates.items() if v >= threshold]


# ---------------------------------------------------------------------------
# Observer effect (siphon / focus)
# ---------------------------------------------------------------------------

def apply_observer(state: WorldState, obs_x: float, obs_y: float,
                   radius: float, pressure: float = 0.1) -> None:
    """
    Observer attention acts as selective pressure:
    points within the beam gain energy; distant ones lose a tiny fraction.
    """
    for pt in state.active:
        dist = math.hypot(pt.x - obs_x, pt.y - obs_y)
        if dist <= radius:
            pt.energy = min(5.0, pt.energy * (1 + pressure * (1 - dist / radius)))
        else:
            pt.energy = max(0.01, pt.energy * (1 - pressure * 0.01))


# ---------------------------------------------------------------------------
# Full simulation tick
# ---------------------------------------------------------------------------

def tick(state: WorldState, new_points: Optional[List[DataPoint]] = None,
         obs_x: float = 0.5, obs_y: float = 0.5, obs_radius: float = 0.1) -> dict:
    """
    Run one simulation step.
    Returns a metrics dict for the frame.
    """
    state.step += 1

    # 1. Inflow
    if new_points:
        precipitation(state, new_points)

    # 2. Age / liquefaction
    liquefaction(state)

    # 3. Lotka–Volterra predator–prey (if mixed kinds present)
    kinds = {p.kind for p in state.active}
    if "prey" in kinds and "predator" in kinds:
        apply_lotka_volterra(state)

    # 4. Water cycle
    abyss_mutation(state)
    evaporation(state)
    condensation(state)

    # 5. Carrying capacity / sea-rise
    apply_carrying_capacity(state)

    # 6. Observer effect
    apply_observer(state, obs_x, obs_y, obs_radius)

    # 7. KDE terrain synthesis  ← the numpy-fixed path
    state.terrain = synthesize_topology(state)

    # 8. Biome labeling (every 10 steps to save compute)
    if state.step % 10 == 0:
        state.biome_map = compute_biome_map(state.terrain, state.grid_w, state.grid_h)

    # 9. Immortal cell tracking
    update_immortal_candidates(state, state.terrain)

    return {
        "step":         state.step,
        "active":       len(state.active),
        "abyss":        len(state.abyss),
        "atmosphere":   len(state.atmosphere),
        "sea_level":    round(state.sea_level, 4),
        "total_energy": round(state.total_energy, 4),
        "immortal_candidates": len(state.immortal_candidates),
    }


# ---------------------------------------------------------------------------
# Hibernation
# ---------------------------------------------------------------------------

def check_hibernation(state: WorldState) -> bool:
    """Returns True if the world should hibernate (Q=0 inflow, zero active)."""
    return len(state.active) == 0
