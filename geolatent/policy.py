"""
geolatent/policy.py
Dynamic homeostasis guardrails and AI policy interventions.

BUG FIX: PolicyIntervention was constructed with step=step (which could be None).
         All three call sites now use step_value = state.step or 0.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PolicyIntervention:
    step:       int
    kind:       str        # "sea_rise" | "temperature_boost" | "siphon" | "prune"
    detail:     str
    roi:        float = 0.5
    params:     dict  = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step":   self.step,
            "kind":   self.kind,
            "detail": self.detail,
            "roi":    self.roi,
            "params": self.params,
        }


class PolicyAgent:
    """
    Closed-loop AI controller monitoring topological health.
    Uses EMA smoothing to prevent erratic over-corrections.
    """

    _BIAS_THRESHOLD      = 0.60    # below → raise sea level
    _STABILITY_THRESHOLD = 0.40    # below → boost temperature
    _ENTROPY_THRESHOLD   = 3.10    # above → schedule pruning
    _EMA_ALPHA           = 0.3

    def __init__(self, state):
        self._ema_bias      = 1.0
        self._ema_stability = 1.0
        self._ema_entropy   = 1.5
        self._last_step     = -1

    def evaluate(self, state, controls: dict) -> list[PolicyIntervention]:
        """
        Check current world health and emit zero or more interventions.
        Returns a list of PolicyIntervention objects (may be empty).
        """
        step_value = state.step or 0   # BUG FIX: never None

        # Only evaluate every 5 steps to avoid spam
        if step_value - self._last_step < 5:
            return []
        self._last_step = step_value

        interventions: list[PolicyIntervention] = []

        # Gather metrics
        terrain = state.terrain
        flat: list[float] = []
        if terrain:
            for row in terrain:
                for v in (row if isinstance(row, list) else row.tolist()):
                    flat.append(float(v))

        if not flat:
            return []

        n    = len(flat)
        mu   = sum(flat) / n
        sig  = math.sqrt(sum((v - mu) ** 2 for v in flat) / n) or 1.0
        above = sum(1 for v in flat if v > mu) / n
        bias  = 1.0 - abs(above - 0.5) * 2.0

        # Shannon entropy
        bins   = [0] * 16
        mn, mx = min(flat), max(flat)
        rng    = max(mx - mn, 1e-9)
        for v in flat:
            bins[min(15, int((v - mn) / rng * 16))] += 1
        entropy = -sum(
            (c / n) * math.log2(c / n) for c in bins if c > 0
        )

        stability = max(0.0, min(1.0, 1.0 - entropy / 4.0))

        # EMA smoothing
        self._ema_bias      = self._ema(bias,      self._ema_bias)
        self._ema_stability = self._ema(stability,  self._ema_stability)
        self._ema_entropy   = self._ema(entropy,    self._ema_entropy)

        # ── Intervention 1: raise sea level if bias too low ────────────────
        if self._ema_bias < self._BIAS_THRESHOLD:
            new_sea = min(0.9, state.sea_level + 0.02)
            state.sea_level = new_sea
            interventions.append(PolicyIntervention(   # BUG FIX: step=step_value
                step   = step_value,
                kind   = "sea_rise",
                detail = f"Bias control {self._ema_bias:.2f} < {self._BIAS_THRESHOLD} — sea raised to {new_sea:.3f}",
                roi    = 0.6,
                params = {"new_sea_level": new_sea, "ema_bias": self._ema_bias},
            ))

        # ── Intervention 2: boost temperature if stability critical ────────
        if self._ema_stability < self._STABILITY_THRESHOLD:
            new_temp = min(3.0, state.temperature + 0.15)
            state.temperature = new_temp
            interventions.append(PolicyIntervention(   # BUG FIX: step=step_value
                step   = step_value,
                kind   = "temperature_boost",
                detail = f"Stability {self._ema_stability:.2f} < {self._STABILITY_THRESHOLD} — temperature raised to {new_temp:.2f}",
                roi    = 0.7,
                params = {"new_temperature": new_temp, "ema_stability": self._ema_stability},
            ))

        # ── Intervention 3: Gaussian pruning on entropy spike ─────────────
        if self._ema_entropy > self._ENTROPY_THRESHOLD:
            self._gaussian_smooth(state)
            interventions.append(PolicyIntervention(   # BUG FIX: step=step_value
                step   = step_value,
                kind   = "prune",
                detail = f"Entropy {self._ema_entropy:.2f} > {self._ENTROPY_THRESHOLD} — Gaussian smoothing applied",
                roi    = 0.8,
                params = {"ema_entropy": self._ema_entropy},
            ))

        return interventions

    def _ema(self, current: float, previous: float) -> float:
        a = self._EMA_ALPHA
        return a * current + (1 - a) * previous

    @staticmethod
    def _gaussian_smooth(state) -> None:
        """Apply a simple box-kernel smoothing pass to the terrain."""
        terrain = state.terrain
        if not terrain:
            return
        rows = len(terrain)
        cols = len(terrain[0]) if rows else 0
        new_t = []
        for r in range(rows):
            row = []
            for c in range(cols):
                neighbours = []
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < rows and 0 <= nc < cols:
                            v = terrain[nr][nc] if isinstance(terrain[nr], list) else float(terrain[nr][nc])
                            neighbours.append(v)
                row.append(sum(neighbours) / len(neighbours))
            new_t.append(row)
        state.terrain = new_t
