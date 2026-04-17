"""
geolatent/engine.py
Orchestration loop — wraps WorldState + all subsystems into a single
GeolatentEngine object that the API and CLI both talk to.
"""
from __future__ import annotations

import copy
import json
import os
import time
from typing import Any, Iterator, List, Optional

from geolatent.simulator import (
    WorldState, DataPoint,
    tick, get_immortal_cells_local, check_hibernation,
    synthesize_topology, compute_biome_map,
)
from geolatent.metrics  import compute_report
from geolatent.mesh     import build_scene
from geolatent.policy   import PolicyAgent


class GeolatentEngine:
    """
    Single-world simulation engine.
    All mutable state lives on self.state (WorldState).
    Thread-safety: the engine is not thread-safe — callers must serialise access
    or use asyncio locks if multiple WS clients call step_once() concurrently.
    """

    def __init__(
        self,
        grid_w: int = 40,
        grid_h: int = 24,
        sigma: float = 2.8,
        carrying_capacity: float = 500.0,
        save_dir: Optional[str] = None,
    ):
        self.state = WorldState(
            grid_w=grid_w,
            grid_h=grid_h,
            sigma=sigma,
            carrying_capacity=carrying_capacity,
        )
        self._paused         = False
        self._controls: dict = {
            "variance":         1.0,
            "temperature":      1.0,
            "inflow_mode":      "neutral",
            "inject_anomaly":   False,
            "siphon_source":    None,
            "siphon_target":    None,
            "siphon_fraction":  0.0,
            "observer_x":       0.5,
            "observer_y":       0.5,
            "observer_radius":  0.1,
            "observer_pressure":0.1,
        }
        self._policy         = PolicyAgent(self.state)
        self._last_frame:  dict = {}
        self._last_scene:  dict = {}
        self._last_report: dict = {}
        self._save_dir       = save_dir
        self._run_id: Optional[str] = None
        self._interventions: List[dict] = []

        # Compute initial terrain
        self._refresh()

    # ── Controls ─────────────────────────────────────────────────────────

    def get_controls(self) -> dict:
        return copy.copy(self._controls)

    def set_controls(self, patch: dict) -> None:
        for k, v in patch.items():
            if k in self._controls:
                self._controls[k] = v
        # Apply immediate effects
        self.state.sigma       = max(0.1, float(self._controls.get("variance", 1.0)) * 2.8)
        self.state.temperature = max(0.01, float(self._controls.get("temperature", 1.0)))

    def set_observer(self, x: float, y: float, radius: float, pressure: float = 0.1) -> None:
        self._controls["observer_x"]        = x
        self._controls["observer_y"]        = y
        self._controls["observer_radius"]   = radius
        self._controls["observer_pressure"] = pressure

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def step_once(self) -> dict:
        """Advance the simulation by exactly one tick."""
        from geolatent.scenarios import generate_inflow
        new_pts = generate_inflow(
            self.state,
            mode=self._controls.get("inflow_mode", "neutral"),
            inject_anomaly=bool(self._controls.get("inject_anomaly", False)),
        )
        # Reset one-shot flag
        if self._controls.get("inject_anomaly"):
            self._controls["inject_anomaly"] = False

        metrics = tick(
            self.state,
            new_points=new_pts,
            obs_x=float(self._controls.get("observer_x",       0.5)),
            obs_y=float(self._controls.get("observer_y",       0.5)),
            obs_radius=float(self._controls.get("observer_radius", 0.1)),
        )

        # Policy agent homeostasis
        interventions = self._policy.evaluate(self.state, self._controls)
        self._interventions.extend(interventions)
        if len(self._interventions) > 100:
            self._interventions = self._interventions[-100:]

        self._refresh(metrics=metrics, interventions=interventions)
        return self._last_frame

    def run_once(self) -> dict:
        """Alias for step_once (used by POST /run_once)."""
        return self.step_once()

    def run(self, steps: int, inflow_iterator: Optional[Iterator] = None) -> None:
        """Run N steps (blocking — use in CLI / background tasks)."""
        for _ in range(steps):
            if self._paused:
                time.sleep(0.05)
                continue
            if inflow_iterator:
                try:
                    batch = next(inflow_iterator)
                    for pt in batch:
                        self.state.active.append(pt)
                except StopIteration:
                    pass
            self.step_once()
            if self._save_dir:
                self._persist_frame()
            if check_hibernation(self.state):
                break

    # ── Lookahead (ghost simulation) ──────────────────────────────────────

    def lookahead(self, steps: int = 3) -> dict:
        """
        Run a shadow copy of the simulation `steps` ticks into the future.
        Returns a scene dict for the ghost wireframe overlay.
        Does NOT mutate self.state.
        """
        import copy as _copy
        shadow_state = _copy.deepcopy(self.state)
        shadow_controls = _copy.copy(self._controls)

        for _ in range(steps):
            from geolatent.scenarios import generate_inflow
            new_pts = generate_inflow(
                shadow_state,
                mode=shadow_controls.get("inflow_mode", "neutral"),
                inject_anomaly=False,
            )
            tick(
                shadow_state,
                new_points=new_pts,
                obs_x=float(shadow_controls.get("observer_x",      0.5)),
                obs_y=float(shadow_controls.get("observer_y",      0.5)),
                obs_radius=float(shadow_controls.get("observer_radius", 0.1)),
            )

        return build_scene(shadow_state)

    # ── Frame / Scene / Report ────────────────────────────────────────────

    def current_frame(self) -> dict:
        return copy.deepcopy(self._last_frame)

    def current_scene(self) -> dict:
        return copy.deepcopy(self._last_scene)

    def current_report(self) -> dict:
        return copy.deepcopy(self._last_report)

    def snapshot(self) -> dict:
        return {
            "step":     self.state.step,
            "frame":    self.current_frame(),
            "scene":    self.current_scene(),
            "report":   self.current_report(),
            "controls": self.get_controls(),
            "ts":       time.time(),
        }

    # ── Internal ─────────────────────────────────────────────────────────

    def _refresh(self, metrics: Optional[dict] = None, interventions: Optional[list] = None):
        """Rebuild cached frame / scene / report from current WorldState."""
        if metrics is None:
            metrics = {
                "step":         self.state.step,
                "active":       len(self.state.active),
                "abyss":        len(self.state.abyss),
                "atmosphere":   len(self.state.atmosphere),
                "sea_level":    round(self.state.sea_level, 4),
                "total_energy": round(self.state.total_energy, 4),
                "immortal_candidates": len(self.state.immortal_candidates),
            }

        anomalies = []
        if self.state.terrain:
            rows  = self.state.terrain
            H, W  = len(rows), len(rows[0]) if rows else 0
            flat  = [v for row in rows for v in (row if isinstance(row, list) else row.tolist())]
            if flat:
                mu    = sum(flat) / len(flat)
                sigma = (sum((v - mu) ** 2 for v in flat) / len(flat)) ** 0.5
                thr   = mu + 3 * sigma
                for gy in range(H):
                    for gx in range(W):
                        v = rows[gy][gx] if isinstance(rows[gy], list) else float(rows[gy][gx])
                        if v > thr:
                            anomalies.append({"gx": gx, "gy": gy, "value": round(v, 4)})

        self._last_frame = {
            **metrics,
            "anomalies":     anomalies,
            "interventions": (interventions or [])[:10],
            "hibernating":   check_hibernation(self.state),
        }

        # Scene (mesh + biomes)
        self._last_scene = build_scene(self.state)

        # Report
        self._last_report = compute_report(
            self.state,
            self._last_frame,
            self._interventions,
        )

    def _persist_frame(self) -> None:
        """Write current frame to save_dir as JSON (for replay)."""
        if not self._save_dir:
            return
        os.makedirs(self._save_dir, exist_ok=True)
        path = os.path.join(self._save_dir, f"frame_{self.state.step:06d}.json")
        with open(path, "w") as f:
            json.dump(self.snapshot(), f)
