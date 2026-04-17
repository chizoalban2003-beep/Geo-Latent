"""
geolatent/performance.py
ROI-based performance analytics for the simulation engine.

Grade scale:
  A  stability >= 0.80
  B  stability >= 0.60
  C  stability >= 0.40
  D  stability <  0.40

Exposes:
  compute_performance(state, interventions) -> dict
  GET /performance  — router registered in api.py
"""
from __future__ import annotations

import math
from fastapi import APIRouter, Request

router = APIRouter()


def compute_performance(state, interventions: list) -> dict:
    """
    Score = weighted average of:
      - drift_accuracy    (1 - normalised drift)
      - intervention_roi  (mean ROI of recent interventions)
      - avg_stability     (terrain flatness proxy)

    Returns a dict with score [0,1], grade A-D, and sub-scores.
    """
    terrain = state.terrain
    flat: list[float] = []
    if terrain:
        for row in terrain:
            for v in (row if isinstance(row, list) else row.tolist()):
                flat.append(float(v))

    # Drift accuracy: how close mean is to baseline 1.0
    if flat and state.step:
        mu = sum(flat) / len(flat)
        raw_drift = abs(mu - 1.0) / max(1.0, state.step)
        drift_accuracy = max(0.0, 1.0 - raw_drift * 10)
    else:
        drift_accuracy = 1.0

    # Terrain stability: inverse coefficient of variation
    if flat:
        mu = sum(flat) / len(flat)
        sigma = math.sqrt(sum((v - mu) ** 2 for v in flat) / len(flat))
        cv = sigma / max(1e-9, mu)
        avg_stability = max(0.0, min(1.0, 1.0 - cv))
    else:
        avg_stability = 1.0

    # Intervention ROI
    if interventions:
        intervention_roi = sum(i.get("roi", 0.5) if isinstance(i, dict)
                               else getattr(i, "roi", 0.5)
                               for i in interventions) / len(interventions)
    else:
        intervention_roi = 0.5

    score = round(
        0.35 * drift_accuracy + 0.35 * intervention_roi + 0.30 * avg_stability, 4
    )

    if score >= 0.80:
        grade = "A"
    elif score >= 0.60:
        grade = "B"
    elif score >= 0.40:
        grade = "C"
    else:
        grade = "D"

    return {
        "score":            score,
        "grade":            grade,
        "drift_accuracy":   round(drift_accuracy,   4),
        "intervention_roi": round(intervention_roi, 4),
        "avg_stability":    round(avg_stability,    4),
        "step":             state.step,
        "active":           len(state.active),
        "interventions":    len(interventions),
    }


@router.get("")
async def get_performance(request: Request):
    """Return current-step performance analytics for the running engine."""
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        return {
            "score": 0.0, "grade": "D",
            "drift_accuracy": 0.0, "intervention_roi": 0.5,
            "avg_stability": 0.0, "step": 0, "active": 0, "interventions": 0,
            "error": "engine not ready",
        }
    interventions = getattr(engine, "_interventions", [])
    return compute_performance(engine.state, interventions)
