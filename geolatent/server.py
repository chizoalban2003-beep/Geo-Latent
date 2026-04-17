"""
geolatent/server.py
ASGI entrypoint: uvicorn geolatent.server:app
Initialises engine on app.state before the lifespan runs.
"""
from __future__ import annotations
import os
import sys
from geolatent.api import app


def _init_default_engine():
    """
    Pre-warm a default engine if no external code has set app.state.engine.
    Called at module import time so `uvicorn geolatent.server:app` starts
    with a ready simulation.
    """
    from geolatent.engine    import GeolatentEngine
    from geolatent.scenarios import build_scenario

    scenario_name = os.environ.get("GEOLATENT_DEFAULT_SCENARIO", "neutral_baseline")
    mode = os.environ.get("GEOLATENT_MODE", "production").lower()

    print(
        f"[geo-latent] Warming up engine (scenario={scenario_name}, mode={mode})...",
        file=sys.stderr,
    )
    sc     = build_scenario(scenario_name)
    engine = GeolatentEngine()
    engine._controls["inflow_mode"] = sc.get("mode", "neutral")
    engine.run(3)   # 3 warm-up steps so first /frame is never empty
    app.state.engine = engine
    print(
        f"[geo-latent] Engine ready — step={engine.state.step}, "
        f"active={len(engine.state.active)}, "
        f"inflow={engine._controls['inflow_mode']}",
        file=sys.stderr,
    )


if not getattr(app.state, "engine", None):
    app.state.engine = None   # mark as not loaded before attempting warm-up
    try:
        _init_default_engine()
    except Exception as exc:
        print(
            f"[geo-latent] ERROR: engine warm-up failed — {exc}\n"
            "  Simulation endpoints will return 503 until the engine is loaded.\n"
            "  Fix the error above and restart the server.",
            file=sys.stderr,
        )
