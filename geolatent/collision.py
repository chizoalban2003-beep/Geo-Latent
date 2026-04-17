"""
geolatent/collision.py
Lotka-Volterra predator-prey dynamics extracted from simulator.py.

Exposes:
  lotka_volterra_step(prey_pool, pred_pool, ...) -> (new_prey, new_pred)
  apply_lotka_volterra(state, ...)               -> None  (drop-in replacement)
  run_collision(world_a, world_b, steps)         -> dict  (two-world simulation)
"""
from __future__ import annotations

import math
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from geolatent.simulator import WorldState, DataPoint


# ---------------------------------------------------------------------------
# Core ODE step
# ---------------------------------------------------------------------------

def lotka_volterra_step(
    prey_pool: list,
    pred_pool: list,
    alpha: float = 1.1,
    beta: float = 0.4,
    delta: float = 0.1,
    gamma: float = 0.4,
    dt: float = 0.05,
) -> tuple[float, float]:
    """
    Single Euler step of Lotka-Volterra equations.
    Returns (delta_prey_energy, delta_pred_energy) to apply to each point.

    prey: dx/dt = alpha*x - beta*x*y
    pred: dy/dt = delta*x*y - gamma*y
    """
    x = sum(p.energy for p in prey_pool) / max(1, len(prey_pool))
    y = sum(p.energy for p in pred_pool) / max(1, len(pred_pool))

    dx = (alpha * x - beta  * x * y) * dt
    dy = (delta * x * y - gamma * y) * dt
    return dx, dy


def apply_lotka_volterra(
    state,
    alpha: float = 1.1,
    beta: float = 0.4,
    delta: float = 0.1,
    gamma: float = 0.4,
    dt: float = 0.05,
) -> None:
    """
    Mutates point energies in-place for the active pool.
    Drop-in replacement for the original simulator.apply_lotka_volterra.
    """
    prey = [p for p in state.active if p.kind == "prey"]
    pred = [p for p in state.active if p.kind == "predator"]
    if not prey or not pred:
        return

    dx, dy = lotka_volterra_step(prey, pred, alpha, beta, delta, gamma, dt)

    for p in prey:
        p.energy = max(0.01, p.energy + dx)
    for p in pred:
        p.energy = max(0.01, p.energy + dy)


# ---------------------------------------------------------------------------
# Two-world collision simulation
# ---------------------------------------------------------------------------

def run_collision(world_a, world_b, steps: int = 10) -> dict:
    """
    Simulate Lotka-Volterra interaction between two WorldState pools.
    world_a.active → treated as prey population.
    world_b.active → treated as predator population.

    Returns a summary dict with per-step energy traces and final state.
    Does NOT mutate the original worlds.
    """
    import copy

    prey_pool  = copy.deepcopy(world_a.active)
    pred_pool  = copy.deepcopy(world_b.active)

    trace: list[dict] = []
    for step in range(steps):
        if not prey_pool or not pred_pool:
            break
        dx, dy = lotka_volterra_step(prey_pool, pred_pool)
        for p in prey_pool:
            p.energy = max(0.01, p.energy + dx)
        for p in pred_pool:
            p.energy = max(0.01, p.energy + dy)

        trace.append({
            "step":       step + 1,
            "prey_mean":  round(sum(p.energy for p in prey_pool) / len(prey_pool), 4),
            "pred_mean":  round(sum(p.energy for p in pred_pool) / len(pred_pool), 4),
            "prey_count": len(prey_pool),
            "pred_count": len(pred_pool),
        })

    return {
        "steps_run":   len(trace),
        "trace":       trace,
        "final_prey_mean": trace[-1]["prey_mean"] if trace else 0.0,
        "final_pred_mean": trace[-1]["pred_mean"] if trace else 0.0,
    }
