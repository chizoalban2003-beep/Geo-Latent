"""
geolatent/server.py
ASGI entrypoint: uvicorn geolatent.server:app
Initialises engine on app.state before the lifespan runs.
"""
from __future__ import annotations
import os
import sys

# Load .env from project root before anything else reads os.environ
def _load_dotenv():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(root, ".env")
    if not os.path.exists(env_path):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path, override=False)
    except ImportError:
        # Fallback: manual parse
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

_load_dotenv()

from geolatent.api import app  # noqa: E402 (must be after env load)


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
