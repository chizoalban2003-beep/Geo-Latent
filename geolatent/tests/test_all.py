"""
geolatent/tests/test_all.py
Comprehensive test suite — all five layers + market expansion modules.
Runs without Postgres, Redis, or network access.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import tempfile
import time

import pytest

# ── Ensure the package root is on sys.path ────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# =============================================================================
# Layer 1 — Ingestion & Security
# =============================================================================

class TestIngestion:
    def test_csv_adapter_basic(self):
        from geolatent.adapters import from_csv_bytes
        csv = b"x,y,energy,kind\n0.2,0.3,1.5,neutral\n0.8,0.7,2.1,predator\n"
        pts = from_csv_bytes(csv)
        assert len(pts) == 2
        assert pts[0].kind == "neutral"
        assert pts[1].kind == "predator"
        assert 0.0 <= pts[0].x <= 1.0

    def test_jsonl_adapter(self):
        from geolatent.adapters import from_jsonl_bytes
        data = b'{"x":0.1,"y":0.2,"energy":1.0,"kind":"prey"}\n{"x":0.9,"y":0.8}\n'
        pts = from_jsonl_bytes(data)
        assert len(pts) == 2
        assert pts[0].kind == "prey"
        assert pts[1].kind == "neutral"   # default

    def test_prototype_pollution_guard(self):
        from geolatent.adapters import _sanitise
        dirty = {"x": 0.5, "__proto__": {"evil": True}, "constructor": "bad", "y": 0.5}
        clean = _sanitise(dirty)
        assert "__proto__"  not in clean
        assert "constructor" not in clean
        assert "x" in clean

    def test_auto_normalise_out_of_range(self):
        from geolatent.adapters import from_csv_bytes
        # Values outside [0,1] should be auto-normalised
        csv = b"x,y\n100,200\n200,400\n150,300\n"
        pts = from_csv_bytes(csv)
        for pt in pts:
            assert 0.0 <= pt.x <= 1.0
            assert 0.0 <= pt.y <= 1.0

    def test_jsonl_ignores_malformed_lines(self):
        from geolatent.adapters import from_jsonl_bytes
        data = b'{"x":0.5,"y":0.5}\nNOT JSON\n{"x":0.3,"y":0.7}\n'
        pts = from_jsonl_bytes(data)
        assert len(pts) == 2


# =============================================================================
# Layer 2 — Physics & Mathematical Engine
# =============================================================================

class TestPhysics:
    def _make_state(self, n: int = 20):
        from geolatent.simulator import WorldState, DataPoint
        import random
        state = WorldState(grid_w=20, grid_h=12, sigma=2.0)
        for _ in range(n):
            state.active.append(DataPoint(
                x=random.random(), y=random.random(),
                energy=random.uniform(0.5, 2.0), kind="neutral",
            ))
        return state

    def test_kde_numpy_produces_terrain(self):
        from geolatent.simulator import synthesize_topology
        state = self._make_state(30)
        terrain = synthesize_topology(state)
        assert len(terrain) == 12
        assert len(terrain[0]) == 20
        assert any(v > 0 for row in terrain for v in row)

    def test_kde_terrain_all_non_negative(self):
        from geolatent.simulator import synthesize_topology
        state = self._make_state(50)
        terrain = synthesize_topology(state)
        for row in terrain:
            for v in row:
                assert v >= 0.0, f"Negative terrain value: {v}"

    def test_lotka_volterra_changes_energy(self):
        from geolatent.simulator import WorldState, DataPoint, apply_lotka_volterra
        state = WorldState()
        for _ in range(10):
            state.active.append(DataPoint(x=0.3, y=0.5, energy=1.0, kind="prey"))
        for _ in range(5):
            state.active.append(DataPoint(x=0.7, y=0.5, energy=1.5, kind="predator"))
        before_prey = sum(p.energy for p in state.active if p.kind == "prey")
        apply_lotka_volterra(state)
        after_prey = sum(p.energy for p in state.active if p.kind == "prey")
        assert after_prey != before_prey

    def test_water_cycle_liquefaction(self):
        from geolatent.simulator import WorldState, DataPoint, liquefaction
        state = WorldState()
        for _ in range(5):
            pt = DataPoint(x=0.5, y=0.5, energy=1.0)
            pt.age = 100   # already stale
            state.active.append(pt)
        for _ in range(3):
            state.active.append(DataPoint(x=0.5, y=0.5, energy=1.0))
        liquefaction(state, stale_threshold=50)
        assert len(state.abyss) == 5
        assert len(state.active) == 3

    def test_water_cycle_condensation(self):
        from geolatent.simulator import WorldState, DataPoint, condensation
        import random
        random.seed(42)
        state = WorldState()
        for _ in range(50):
            state.atmosphere.append(DataPoint(x=random.random(), y=random.random()))
        condensation(state, condense_rate=1.0)   # 100% condense
        assert len(state.active) == 50
        assert len(state.atmosphere) == 0

    def test_biome_labeling(self):
        from geolatent.simulator import label_biome
        label = label_biome(0.05, 0.05)
        assert "—" in label   # hybrid format
        assert len(label) > 5

    def test_immortal_candidate_accumulation(self):
        from geolatent.simulator import WorldState, DataPoint, synthesize_topology, update_immortal_candidates
        state = WorldState(grid_w=10, grid_h=8)
        for _ in range(10):
            state.active.append(DataPoint(x=0.5, y=0.5, energy=1.0))
        state.terrain = synthesize_topology(state)
        for _ in range(5):
            update_immortal_candidates(state, state.terrain)
        assert len(state.immortal_candidates) > 0

    def test_full_tick(self):
        from geolatent.simulator import WorldState, DataPoint, tick
        state = WorldState(grid_w=12, grid_h=8)
        new_pts = [DataPoint(x=0.5, y=0.5, energy=1.0) for _ in range(10)]
        metrics = tick(state, new_points=new_pts)
        assert metrics["step"] == 1
        assert state.terrain is not None


# =============================================================================
# Layer 3 — Autonomic Systems & Homeostasis
# =============================================================================

class TestHomeostasis:
    def test_policy_agent_sea_rise(self):
        from geolatent.simulator import WorldState, DataPoint, synthesize_topology
        from geolatent.policy    import PolicyAgent
        import random

        state = WorldState(grid_w=10, grid_h=8)
        # Force very skewed terrain so bias_control < 0.6
        for _ in range(30):
            state.active.append(DataPoint(x=random.uniform(0.8, 1.0),
                                           y=random.uniform(0.8, 1.0), energy=3.0))
        state.terrain = synthesize_topology(state)
        state.step = 10

        agent = PolicyAgent(state)
        # Run multiple evaluations to let EMA converge
        for _ in range(5):
            state.step += 5
            agent.evaluate(state, {})

        # Sea level should have risen above baseline 0.15
        assert state.sea_level >= 0.15

    def test_policy_intervention_step_not_none(self):
        """Regression test for the step=None bug."""
        from geolatent.policy import PolicyIntervention
        pi = PolicyIntervention(step=0, kind="sea_rise", detail="test", roi=0.5)
        assert pi.step == 0
        assert isinstance(pi.to_dict(), dict)

    def test_entropy_threshold(self):
        from geolatent.metrics import _shannon_entropy
        flat_values    = [1.0] * 100
        chaotic_values = list(range(100))
        assert _shannon_entropy(flat_values)    < 1.0
        assert _shannon_entropy(chaotic_values) > 3.0

    def test_ema_converges(self):
        from geolatent.metrics import _ema
        val = 1.0
        for _ in range(100):
            val = _ema(0.0, val, alpha=0.2)
        assert val < 0.01   # should converge close to 0


# =============================================================================
# Layer 4 — Rendering & Sensory
# =============================================================================

class TestRendering:
    def test_ascii_render(self):
        from geolatent.visualization import render_ascii
        terrain = [[float(c + r) / 20.0 for c in range(10)] for r in range(6)]
        result  = render_ascii(terrain, sea_level=0.2)
        assert isinstance(result, str)
        assert len(result.splitlines()) >= 6

    def test_scene_build(self):
        from geolatent.simulator import WorldState, DataPoint, synthesize_topology
        from geolatent.mesh      import build_scene
        state = WorldState(grid_w=10, grid_h=8)
        state.active = [DataPoint(x=0.5, y=0.5, energy=1.0) for _ in range(5)]
        state.terrain = synthesize_topology(state)
        scene = build_scene(state)
        assert "vertices" in scene
        assert "faces"    in scene
        assert len(scene["vertices"]) == 10 * 8
        assert len(scene["faces"])    > 0
        # Every face references valid vertex indices
        n = len(scene["vertices"])
        for f in scene["faces"]:
            assert all(0 <= i < n for i in f)

    def test_obj_export(self):
        from geolatent.simulator import WorldState, DataPoint, synthesize_topology
        from geolatent.mesh      import write_obj
        state = WorldState(grid_w=8, grid_h=6)
        state.active  = [DataPoint(x=0.5, y=0.5, energy=1.0)]
        state.terrain = synthesize_topology(state)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "terrain.obj")
            write_obj(state, path)
            with open(path) as f:
                content = f.read()
        assert content.startswith("# Geo-latent")
        assert "v " in content
        assert "f " in content

    def test_biome_lore_procedural(self):
        from geolatent.biome_lore import _deterministic_lore
        lore = _deterministic_lore("The Fracture Bloom — High-Gradient Drift Zone")
        assert isinstance(lore, str)
        assert len(lore) > 20

    def test_biome_slug(self):
        from geolatent.biome_lore import _slug
        assert _slug("The Fracture Bloom — High-Gradient Drift Zone") == "the-fracture-bloom"
        assert _slug("The Null Fens — Sparse Anomaly Wetland") == "the-null-fens"


# =============================================================================
# Layer 5 — Post-game Analytics
# =============================================================================

class TestAnalytics:
    def test_stability_index_range(self):
        from geolatent.simulator import WorldState, DataPoint, synthesize_topology
        from geolatent.metrics   import compute_report
        state = WorldState(grid_w=10, grid_h=8)
        state.active = [DataPoint(x=0.5, y=0.5, energy=1.0) for _ in range(20)]
        state.terrain = synthesize_topology(state)
        state.step = 10
        frame  = {"step": 10, "sea_level": 0.15, "active": 20, "total_energy": 10.0}
        report = compute_report(state, frame, [])
        assert 0.0 <= report["stability_index"] <= 1.0
        assert report["verdict"] in ("Stabilized Manifold", "Systemic Collapse", "Transitional State", "Initializing")

    def test_immortal_cells_tracked(self):
        from geolatent.simulator import WorldState, DataPoint, synthesize_topology, update_immortal_candidates, get_immortal_cells_local
        state = WorldState(grid_w=8, grid_h=6)
        state.active = [DataPoint(x=0.5, y=0.5, energy=1.0) for _ in range(15)]
        state.terrain = synthesize_topology(state)
        # Fake 2000 ticks for one cell
        state.immortal_candidates[(4, 3)] = 2000
        immortals = get_immortal_cells_local(state)
        assert len(immortals) == 1
        assert immortals[0]["gx"] == 4

    def test_report_has_all_keys(self):
        from geolatent.simulator import WorldState, DataPoint, synthesize_topology
        from geolatent.metrics   import compute_report
        state = WorldState(grid_w=8, grid_h=6)
        state.active  = [DataPoint(x=0.5, y=0.5, energy=1.0)]
        state.terrain = synthesize_topology(state)
        state.step    = 1
        report = compute_report(state, {"step": 1}, [])
        required = {"stability_index", "verdict", "entropy", "drift", "bias_control",
                    "energy_flux", "immortal_cells", "intervention_roi"}
        assert required.issubset(set(report.keys()))


# =============================================================================
# Engine integration tests
# =============================================================================

class TestEngine:
    def test_engine_step_produces_frame(self):
        from geolatent.engine import GeolatentEngine
        engine = GeolatentEngine(grid_w=12, grid_h=8)
        frame = engine.step_once()
        assert frame["step"] == 1
        assert "sea_level" in frame

    def test_engine_run_multiple_steps(self):
        from geolatent.engine import GeolatentEngine
        engine = GeolatentEngine(grid_w=12, grid_h=8)
        engine.run(5)
        assert engine.state.step == 5

    def test_engine_controls(self):
        from geolatent.engine import GeolatentEngine
        engine = GeolatentEngine(grid_w=12, grid_h=8)
        engine.set_controls({"variance": 2.0, "temperature": 0.5})
        ctrl = engine.get_controls()
        assert ctrl["variance"]    == 2.0
        assert ctrl["temperature"] == 0.5

    def test_engine_observer(self):
        from geolatent.engine import GeolatentEngine
        engine = GeolatentEngine(grid_w=12, grid_h=8)
        engine.set_observer(0.3, 0.7, 0.15)
        ctrl = engine.get_controls()
        assert ctrl["observer_x"]      == 0.3
        assert ctrl["observer_y"]      == 0.7
        assert ctrl["observer_radius"] == 0.15

    def test_engine_pause_resume(self):
        from geolatent.engine import GeolatentEngine
        engine = GeolatentEngine(grid_w=8, grid_h=6)
        engine.pause()
        assert engine._paused
        engine.resume()
        assert not engine._paused

    def test_engine_snapshot_roundtrip(self):
        from geolatent.engine import GeolatentEngine
        engine = GeolatentEngine(grid_w=8, grid_h=6)
        engine.run(3)
        snap = engine.snapshot()
        assert snap["step"] == 3
        assert "frame" in snap
        assert "scene" in snap
        assert "report" in snap

    def test_engine_save_replay(self):
        from geolatent.engine     import GeolatentEngine
        from geolatent.persistence import iter_replay
        with tempfile.TemporaryDirectory() as d:
            engine = GeolatentEngine(grid_w=8, grid_h=6, save_dir=d)
            engine.run(4)
            frames = list(iter_replay(d))
        assert len(frames) == 4
        assert frames[-1]["step"] == 4


# =============================================================================
# Market expansion — Gaming
# =============================================================================

class TestGaming:
    def test_world_seed_gdelt(self):
        import asyncio
        from geolatent.gaming import world_seed
        from unittest.mock import MagicMock
        result = asyncio.run(world_seed("gdelt"))
        assert "seed" in result
        assert result["dataset"] == "gdelt"

    def test_world_seed_unknown_returns_list(self):
        import asyncio
        from geolatent.gaming import world_seed
        result = asyncio.run(world_seed("unknown_dataset"))
        assert "available_seeds" in result

    def test_player_registry_prune(self):
        from geolatent.gaming import _players, _prune_players
        _players["stale"] = {"ts": time.time() - 120}   # 2 minutes old
        _players["fresh"] = {"ts": time.time()}
        _prune_players()
        assert "stale" not in _players
        assert "fresh" in _players
        _players.pop("fresh", None)


# =============================================================================
# Market expansion — Education
# =============================================================================

class TestEducation:
    def test_tour_pack_exists(self):
        import asyncio
        from geolatent.education import get_tour
        result = asyncio.run(get_tour("intro-to-kde"))
        assert result["title"] == "Introduction to KDE Terrain Synthesis"
        assert len(result["steps"]) == 5

    def test_glossary_has_kde(self):
        import asyncio
        from geolatent.education import glossary
        result = asyncio.run(glossary())
        assert "KDE (Kernel Density Estimation)" in result["terms"]

    def test_teaching_datasets(self):
        import asyncio
        from geolatent.education import teaching_datasets
        result = asyncio.run(teaching_datasets())
        assert len(result["datasets"]) >= 3


# =============================================================================
# Market expansion — Billing
# =============================================================================

class TestBilling:
    def test_free_tier_limits(self):
        from geolatent.billing import PLANS, check_gate
        assert not PLANS["free"]["limits"]["sdk_exports"]
        assert not PLANS["free"]["limits"]["repro_bundles"]
        assert not check_gate("unknown_tenant", "sdk_exports")

    def test_studio_tier_gates(self):
        from geolatent.billing import _subscriptions, check_gate
        _subscriptions["test_tenant"] = {"tier": "studio", "status": "active"}
        assert check_gate("test_tenant", "sdk_exports")
        assert check_gate("test_tenant", "gaming_ws")
        del _subscriptions["test_tenant"]

    def test_plans_list(self):
        import asyncio
        from geolatent.billing import list_plans
        result = asyncio.run(list_plans())
        assert set(result["plans"].keys()) == {"free", "research", "studio", "enterprise"}


# =============================================================================
# Auth
# =============================================================================

class TestAuth:
    def test_issue_and_verify_jwt(self):
        from geolatent.auth import issue_jwt, _verify_hs256
        token = issue_jwt({"tenant_id": "t1", "principal_id": "p1", "role": "admin"},
                          secret="test-secret", ttl=3600)
        payload = _verify_hs256(token, secret="test-secret")
        assert payload["tenant_id"]    == "t1"
        assert payload["principal_id"] == "p1"

    def test_expired_jwt_rejected(self):
        from geolatent.auth import issue_jwt, _verify_hs256
        token = issue_jwt({"tenant_id": "t1"}, secret="test-secret", ttl=-1)
        with pytest.raises(ValueError, match="expired"):
            _verify_hs256(token, secret="test-secret")

    def test_tampered_jwt_rejected(self):
        from geolatent.auth import issue_jwt, _verify_hs256
        token = issue_jwt({"tenant_id": "t1"}, secret="test-secret")
        tampered = token[:-4] + "XXXX"
        with pytest.raises(ValueError):
            _verify_hs256(tampered, secret="test-secret")

    def test_password_hash_verify(self):
        from geolatent.auth import _hash_password, _verify_password
        h = _hash_password("correct-horse-battery-staple")
        assert _verify_password("correct-horse-battery-staple", h)
        assert not _verify_password("wrong-password", h)

    def test_dev_header_auth(self, monkeypatch):
        import asyncio
        from unittest.mock import MagicMock
        import geolatent.auth as auth_module
        monkeypatch.setattr(auth_module, "ALLOW_DEV_HDR", True)

        from fastapi import Request
        scope = {"type": "http", "method": "GET", "path": "/", "query_string": b"",
                 "headers": [(b"x-tenant-id", b"myorg"), (b"x-principal-id", b"alice"),
                              (b"x-role", b"operator")]}
        req = Request(scope)
        ctx = auth_module._parse_dev_headers(req)
        assert ctx["tenant_id"]    == "myorg"
        assert ctx["principal_id"] == "alice"
        assert ctx["role"]         == "operator"


# =============================================================================
# Adapters — batch iteration
# =============================================================================

class TestAdapters:
    def test_iter_batches(self):
        from geolatent.simulator import DataPoint
        from geolatent.adapters  import iter_batches
        pts = [DataPoint(x=float(i)/100, y=0.5) for i in range(55)]
        batches = list(iter_batches(pts, batch_size=20))
        assert len(batches) == 3
        assert sum(len(b) for b in batches) == 55
