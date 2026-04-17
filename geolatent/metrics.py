"""
geolatent/metrics.py
Ecological impact report metrics — drift, bias, stability, entropy.
"""
from __future__ import annotations

import math
from typing import Any


def _shannon_entropy(values: list[float]) -> float:
    """H(X) = -Σ p(x) log2 p(x) over a histogram of terrain values."""
    if not values:
        return 0.0
    mn, mx = min(values), max(values)
    if mx == mn:
        return 0.0
    bins = 16
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - mn) / (mx - mn) * bins))
        counts[idx] += 1
    n = len(values)
    h = 0.0
    for c in counts:
        if c:
            p = c / n
            h -= p * math.log2(p)
    return round(h, 4)


def _ema(current: float, previous: float, alpha: float = 0.2) -> float:
    """EMA_t = α·p_t + (1−α)·EMA_{t-1}"""
    return round(alpha * current + (1 - alpha) * previous, 4)


def compute_report(state, frame: dict, interventions: list) -> dict:
    """
    Build the full ecological metrics report for one simulation step.
    Returns a dict suitable for /report and the Stability Index calculation.
    """
    terrain = state.terrain
    if terrain is None:
        return _empty_report(frame)

    # Flatten terrain
    flat: list[float] = []
    for row in terrain:
        for v in (row if isinstance(row, list) else row.tolist()):
            flat.append(float(v))

    if not flat:
        return _empty_report(frame)

    n = len(flat)
    mu = sum(flat) / n
    variance = sum((v - mu) ** 2 for v in flat) / n
    sigma    = math.sqrt(variance)

    # Shannon entropy
    entropy = _shannon_entropy(flat)

    # Drift — mean absolute change per step (approximate from frame)
    drift = round(abs(mu - 1.0) / max(1.0, state.step), 4) if state.step else 0.0

    # Bias — skewness proxy: fraction of terrain above mean
    above_mean = sum(1 for v in flat if v > mu) / n
    bias_control = round(1.0 - abs(above_mean - 0.5) * 2, 4)

    # Average stability from policy interventions
    intervention_roi = (
        sum(i.get("roi", 0.0) for i in interventions) / max(1, len(interventions))
        if interventions else 0.5
    )

    # Stability Index  S = ∫ROI(t)dt / TotalEntropy
    total_entropy = max(0.001, entropy * max(1, state.step))
    cumulative_roi = intervention_roi * state.step
    stability_index = round(
        min(1.0, max(0.0, cumulative_roi / total_entropy)), 4
    ) if state.step else 0.75

    # Immortal cells
    immortal = [
        {"gx": k[0], "gy": k[1], "ticks": v}
        for k, v in state.immortal_candidates.items()
        if v >= 2000
    ]

    # Energy flux — ratio of active to total pool size
    total_pool = max(1, len(state.active) + len(state.abyss) + len(state.atmosphere))
    energy_flux = round(len(state.active) / total_pool, 4)

    verdict = (
        "Stabilized Manifold"
        if stability_index >= 0.7
        else "Systemic Collapse"
        if stability_index < 0.4
        else "Transitional State"
    )

    return {
        "step":              state.step,
        "stability_index":   stability_index,
        "verdict":           verdict,
        "entropy":           entropy,
        "drift":             drift,
        "bias_control":      bias_control,
        "energy_flux":       energy_flux,
        "terrain_mu":        round(mu,    4),
        "terrain_sigma":     round(sigma, 4),
        "sea_level":         round(state.sea_level, 4),
        "active":            len(state.active),
        "abyss":             len(state.abyss),
        "atmosphere":        len(state.atmosphere),
        "immortal_cells":    immortal,
        "intervention_roi":  round(intervention_roi, 4),
        "interventions_log": [_fmt_intervention(i) for i in interventions[-5:]],
    }


def _empty_report(frame: dict) -> dict:
    return {
        "step":            frame.get("step", 0),
        "stability_index": 0.75,
        "verdict":         "Initializing",
        "entropy":         0.0,
        "drift":           0.0,
        "bias_control":    1.0,
        "energy_flux":     0.0,
        "terrain_mu":      0.0,
        "terrain_sigma":   0.0,
        "sea_level":       0.15,
        "active":          0,
        "abyss":           0,
        "atmosphere":      0,
        "immortal_cells":  [],
        "intervention_roi":0.5,
        "interventions_log": [],
    }


def _fmt_intervention(i: Any) -> dict:
    if isinstance(i, dict):
        return i
    return {"type": str(type(i).__name__), "detail": str(i)}
