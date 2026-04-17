"""geolatent/demo.py — quick smoke-test demo that runs without a server."""
from __future__ import annotations
from geolatent.engine        import GeolatentEngine
from geolatent.visualization import render_ascii


def run_demo():
    print("=== Geo-latent v3.0 demo ===")
    engine = GeolatentEngine(grid_w=40, grid_h=24)
    engine._controls["inflow_mode"] = "neutral_to_predatory"

    for step in range(12):
        engine.step_once()
        if (step + 1) % 4 == 0:
            report = engine.current_report()
            print(f"\nStep {step+1}: S={report['stability_index']}  "
                  f"entropy={report['entropy']}  "
                  f"verdict={report['verdict']}")
            print(render_ascii(engine.state.terrain, engine.state.sea_level))

    print("\nFinal report:")
    r = engine.current_report()
    for k, v in r.items():
        if k not in ("interventions_log", "immortal_cells"):
            print(f"  {k}: {v}")


if __name__ == "__main__":
    run_demo()
