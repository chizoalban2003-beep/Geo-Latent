"""
geolatent/server.py
ASGI entrypoint: uvicorn geolatent.server:app
Initialises engine on app.state before the lifespan runs.
"""
from __future__ import annotations
import os
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
    sc     = build_scenario(scenario_name)
    engine = GeolatentEngine()
    engine._controls["inflow_mode"] = sc.get("mode", "neutral")
    engine.run(3)   # 3 warm-up steps so first /frame is never empty
    app.state.engine = engine


if not getattr(app.state, "engine", None):
    try:
        _init_default_engine()
    except Exception as exc:
        import sys
        print(f"[geo-latent] WARNING: engine warm-up failed ({exc})", file=sys.stderr)
