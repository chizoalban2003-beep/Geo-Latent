"""
geolatent/cli.py
Command-line entrypoint.
  python3 -m geolatent run   [--scenario NAME] [--steps N] [--render] [--save DIR]
  python3 -m geolatent run   [--csv PATH | --jsonl PATH] [--steps N]
  python3 -m geolatent replay --source DIR [--start K] [--limit N]
  python3 -m geolatent serve [--host H] [--port P] [--scenario NAME] [--steps N]
"""
from __future__ import annotations
import argparse, sys


def cmd_run(args):
    from geolatent.engine   import GeolatentEngine
    from geolatent.scenarios import build_scenario
    from geolatent.adapters  import from_file, iter_batches
    from geolatent.visualization import render_ascii

    scenario_name = getattr(args, "scenario", "neutral_baseline") or "neutral_baseline"
    scenario = build_scenario(scenario_name)
    steps    = getattr(args, "steps", None) or scenario.get("steps", 10)
    save_dir = getattr(args, "save", None)
    do_render= getattr(args, "render", False)

    engine = GeolatentEngine(save_dir=save_dir)

    inflow_iter = None
    if getattr(args, "csv", None):
        pts = from_file(args.csv)
        inflow_iter = iter_batches(pts, batch_size=15)
        print(f"Loaded {len(pts)} points from {args.csv}")
    elif getattr(args, "jsonl", None):
        pts = from_file(args.jsonl)
        inflow_iter = iter_batches(pts, batch_size=15)
        print(f"Loaded {len(pts)} points from {args.jsonl}")
    else:
        from geolatent.engine import GeolatentEngine as _
        engine._controls["inflow_mode"] = scenario.get("mode", "neutral")

    print(f"Running scenario '{scenario_name}' for {steps} steps ...")
    engine.run(steps, inflow_iterator=inflow_iter)

    report = engine.current_report()
    print(f"\n=== Report ===")
    print(f"  Stability Index : {report.get('stability_index', '?')}")
    print(f"  Verdict         : {report.get('verdict', '?')}")
    print(f"  Entropy         : {report.get('entropy', '?')}")
    print(f"  Active points   : {report.get('active', '?')}")
    print(f"  Immortal cells  : {len(report.get('immortal_cells', []))}")

    if do_render:
        state = engine.state
        print("\n" + render_ascii(state.terrain, state.sea_level))

    if save_dir:
        print(f"\nSnapshots saved to: {save_dir}/")


def cmd_replay(args):
    from geolatent.persistence   import iter_replay
    from geolatent.visualization import render_ascii
    import json

    source = args.source
    start  = getattr(args, "start", 0) or 0
    limit  = getattr(args, "limit", None)

    for snap in iter_replay(source, start=start, limit=limit):
        frame = snap.get("frame", {})
        print(f"Step {frame.get('step', '?')} | "
              f"S={snap.get('report', {}).get('stability_index', '?')} | "
              f"active={frame.get('active', '?')}")


def cmd_serve(args):
    import uvicorn

    host     = getattr(args, "host", "0.0.0.0") or "0.0.0.0"
    port     = getattr(args, "port", 8000) or 8000
    scenario = getattr(args, "scenario", "neutral_baseline") or "neutral_baseline"
    steps    = getattr(args, "steps", 20) or 20
    save_dir = getattr(args, "save", None)

    # Pre-initialise engine on app.state before serving
    from geolatent.engine    import GeolatentEngine
    from geolatent.scenarios import build_scenario
    from geolatent.api       import app

    sc      = build_scenario(scenario)
    engine  = GeolatentEngine(save_dir=save_dir)
    engine._controls["inflow_mode"] = sc.get("mode", "neutral")
    engine.run(min(steps, 5))   # warm up terrain before first request

    app.state.engine = engine
    print(f"[geo-latent] Serving at http://{host}:{port}/  (scenario={scenario})")
    uvicorn.run(app, host=host, port=int(port), log_level="info")


def main():
    parser = argparse.ArgumentParser(prog="geolatent")
    sub    = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run")
    p_run.add_argument("--scenario", default="neutral_baseline")
    p_run.add_argument("--steps",    type=int, default=10)
    p_run.add_argument("--render",   action="store_true")
    p_run.add_argument("--save",     default=None)
    p_run.add_argument("--csv",      default=None)
    p_run.add_argument("--jsonl",    default=None)

    # replay
    p_rep = sub.add_parser("replay")
    p_rep.add_argument("--source",   required=True)
    p_rep.add_argument("--start",    type=int, default=0)
    p_rep.add_argument("--limit",    type=int, default=None)

    # serve
    p_srv = sub.add_parser("serve")
    p_srv.add_argument("--host",     default="0.0.0.0")
    p_srv.add_argument("--port",     type=int, default=8000)
    p_srv.add_argument("--scenario", default="neutral_baseline")
    p_srv.add_argument("--steps",    type=int, default=20)
    p_srv.add_argument("--save",     default=None)

    args = parser.parse_args()

    if args.command == "run":
        cmd_run(args)
    elif args.command == "replay":
        cmd_replay(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
