"""geolatent/scenarios.py — inflow generators for all built-in scenarios."""
from __future__ import annotations
import math, random
from geolatent.simulator import DataPoint, WorldState


def generate_inflow(state: WorldState, mode: str = "neutral",
                    inject_anomaly: bool = False) -> list[DataPoint]:
    """Return a list of new DataPoints for this tick."""
    pts: list[DataPoint] = []

    if mode == "neutral":
        for _ in range(random.randint(3, 8)):
            pts.append(DataPoint(
                x=random.gauss(0.5, 0.2), y=random.gauss(0.5, 0.2),
                energy=random.uniform(0.5, 1.5), kind="neutral",
            ))

    elif mode == "prey":
        for _ in range(random.randint(4, 10)):
            pts.append(DataPoint(
                x=max(0.0, min(1.0, random.gauss(0.35, 0.15))),
                y=max(0.0, min(1.0, random.gauss(0.5, 0.2))),
                energy=random.uniform(0.8, 1.8), kind="prey",
            ))

    elif mode == "predator":
        for _ in range(random.randint(2, 6)):
            pts.append(DataPoint(
                x=max(0.0, min(1.0, random.gauss(0.65, 0.15))),
                y=max(0.0, min(1.0, random.gauss(0.5, 0.2))),
                energy=random.uniform(1.2, 2.5), kind="predator",
            ))

    elif mode == "neutral_to_predatory":
        # Gradually shifts from neutral to predator over time
        frac = min(1.0, state.step / 20.0)
        n_neu = max(1, int(6 * (1 - frac)))
        n_pre = max(0, int(4 * frac))
        for _ in range(n_neu):
            pts.append(DataPoint(x=random.random(), y=random.random(),
                                  energy=random.uniform(0.5, 1.5), kind="neutral"))
        for _ in range(n_pre):
            pts.append(DataPoint(
                x=max(0.0, min(1.0, random.gauss(0.65, 0.15))),
                y=max(0.0, min(1.0, random.gauss(0.5, 0.2))),
                energy=random.uniform(1.2, 2.5), kind="predator"))

    elif mode == "finance_predator_prey":
        # Legitimate transactions (prey) vs fraud (predator)
        for _ in range(random.randint(5, 12)):
            amount = abs(random.lognormvariate(4, 1))
            hour   = random.gauss(12, 4)
            pts.append(DataPoint(
                x=min(1.0, amount / 1000.0), y=max(0.0, min(1.0, hour / 24.0)),
                energy=random.uniform(0.5, 1.5), kind="prey",
            ))
        if state.step > 3:
            for _ in range(random.randint(1, 4)):
                pts.append(DataPoint(
                    x=random.uniform(0.6, 1.0), y=random.uniform(0.0, 0.15),
                    energy=random.uniform(2.0, 4.0), kind="predator",
                ))

    # Anomaly injection (one-shot spike)
    if inject_anomaly:
        ax = random.uniform(0.1, 0.9)
        ay = random.uniform(0.1, 0.9)
        for _ in range(5):
            pts.append(DataPoint(
                x=max(0.0, min(1.0, ax + random.gauss(0, 0.03))),
                y=max(0.0, min(1.0, ay + random.gauss(0, 0.03))),
                energy=random.uniform(4.0, 6.0), kind="predator",
            ))

    # Clamp coordinates
    for pt in pts:
        pt.x = max(0.0, min(1.0, pt.x))
        pt.y = max(0.0, min(1.0, pt.y))

    return pts


def build_scenario(name: str) -> dict:
    """Return a scenario config dict by name."""
    scenarios = {
        "neutral_baseline":       {"mode": "neutral",             "steps": 20},
        "neutral_to_predatory":   {"mode": "neutral_to_predatory","steps": 20},
        "finance_predator_prey":  {"mode": "finance_predator_prey","steps": 14},
        "fraud-aml":              {"mode": "finance_predator_prey","steps": 14},
        "predator-prey":          {"mode": "predator",            "steps": 14},
    }
    return scenarios.get(name, {"mode": "neutral", "steps": 10})
