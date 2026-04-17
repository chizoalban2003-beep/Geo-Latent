"""
geolatent/api.py
FastAPI Observatory — all runtime, workspace, auth, gaming, education,
billing, and SDK endpoints.

KEY FIX: @app.on_event replaced with @asynccontextmanager lifespan.
         Per-request _connect() replaced with AsyncConnectionPool on app.state.
"""
from __future__ import annotations

import os
import sys
import json
import hashlib
import hmac
import time
import uuid
import base64
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import (
    FastAPI, Request, WebSocket, WebSocketDisconnect,
    Depends, HTTPException, UploadFile, File, status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


# ---------------------------------------------------------------------------
# Lifespan — replaces ALL @app.on_event blocks
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup → yield → shutdown.
    All shared resources (db pool, redis, engine) live on app.state.
    """
    _PLACEHOLDERS = {
        "GEOLATENT_JWT_SECRET":        "changeme",
        "GEOLATENT_AUDIT_SIGNING_KEY": "changeme",
        "GEOLATENT_BUNDLE_SECRET":     "changeme",
    }
    for var, bad in _PLACEHOLDERS.items():
        if os.environ.get(var, bad) == bad:
            print(f"[geo-latent] WARNING: {var} is still a placeholder value — "
                  "rotate before production.", file=sys.stderr)

    # ── Postgres connection pool ─────────────────────────────────────────────
    db_url = os.environ.get("DATABASE_URL", "")
    pool = None
    if db_url:
        try:
            from psycopg_pool import AsyncConnectionPool
            pool = AsyncConnectionPool(
                conninfo=db_url,
                min_size=2,
                max_size=int(os.environ.get("DB_POOL_MAX", "10")),
                open=False,
            )
            await pool.open(wait=True, timeout=15)
            # Initialise schema on first boot
            from geolatent.persistence_db import init_schema
            async with pool.connection() as conn:
                await init_schema(conn)
            print("[geo-latent] Postgres pool open.", file=sys.stderr)
        except Exception as exc:
            print(f"[geo-latent] WARNING: Postgres unavailable ({exc}). "
                  "Running without persistence.", file=sys.stderr)
            pool = None
    app.state.db_pool = pool

    # ── Redis (optional) ────────────────────────────────────────────────────
    app.state.redis = None
    redis_url = os.environ.get("GEOLATENT_REDIS_URL", "")
    if redis_url:
        try:
            import redis.asyncio as aioredis
            rc = aioredis.from_url(redis_url, decode_responses=True)
            await rc.ping()
            app.state.redis = rc
            print("[geo-latent] Redis connected.", file=sys.stderr)
        except Exception as exc:
            print(f"[geo-latent] WARNING: Redis unavailable ({exc}).", file=sys.stderr)

    # ── Engine + observer registry ──────────────────────────────────────────
    # Populated by geolatent/server.py before serve(); None until then.
    if not hasattr(app.state, "engine"):
        app.state.engine = None
    app.state.ws_clients: set[WebSocket] = set()
    app.state.observer_registry: dict = {}   # {tenant_id: {principal_id: {x,y,r,ts}}}

    print("[geo-latent] Observatory online.", file=sys.stderr)
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    for ws in list(app.state.ws_clients):
        try:
            await ws.close()
        except Exception:
            pass
    if pool:
        await pool.close()
    if app.state.redis:
        await app.state.redis.aclose()
    print("[geo-latent] Observatory shut down cleanly.", file=sys.stderr)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Geo-latent Observatory",
    description="Spatial Data-OS — KDE terrain engine with ecological simulation.",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def get_pool(request: Request):
    pool = request.app.state.db_pool
    if pool is None:
        from geolatent.auth import ALLOW_DEV_HDR
        hint = (
            " Set DATABASE_URL in .env to enable persistence, or use dev-header auth "
            "(GEOLATENT_ALLOW_HEADER_DEV=true) for a no-DB demo."
            if not ALLOW_DEV_HDR
            else " Set DATABASE_URL in .env to enable persistence features."
        )
        raise HTTPException(503, "Database not available." + hint)
    return pool


def get_pool_optional(request: Request):
    """Returns pool or None — for endpoints that gracefully degrade without DB."""
    return request.app.state.db_pool


def get_engine(request: Request):
    engine = request.app.state.engine
    if engine is None:
        raise HTTPException(
            503,
            "Simulation engine not loaded. "
            "Restart the server — if it keeps failing, check server logs for the warm-up error.",
        )
    return engine


async def get_auth(request: Request) -> dict:
    """Parse + validate JWT or dev headers. Returns auth context dict."""
    from geolatent.auth import parse_request_auth
    return await parse_request_auth(request)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["core"])
async def health(request: Request):
    return {
        "status": "ok",
        "engine": request.app.state.engine is not None,
        "db": request.app.state.db_pool is not None,
        "redis": request.app.state.redis is not None,
    }


@app.get("/health/detailed", tags=["core"])
async def health_detailed(request: Request):
    from geolatent.auth import ALLOW_DEV_HDR, OIDC_JWKS_URI, GEOLATENT_MODE, _OIDC_SIG_VERIFIED
    engine = request.app.state.engine
    engine_info: dict = {"loaded": engine is not None}
    if engine:
        engine_info.update({
            "step":          engine.state.step,
            "active_points": len(engine.state.active),
            "paused":        engine._paused,
            "inflow_mode":   engine._controls.get("inflow_mode"),
        })
    db_url = os.environ.get("DATABASE_URL", "")
    return {
        "status": "ok",
        "mode":   GEOLATENT_MODE,
        "engine": engine_info,
        "db": {
            "connected": request.app.state.db_pool is not None,
            "configured": bool(db_url),
            "hint": None if db_url else "Set DATABASE_URL in .env to enable persistence.",
        },
        "redis": {
            "connected": request.app.state.redis is not None,
            "configured": bool(os.environ.get("GEOLATENT_REDIS_URL", "")),
        },
        "auth": {
            "dev_headers_enabled": ALLOW_DEV_HDR,
            "oidc_configured":     bool(OIDC_JWKS_URI),
            "oidc_sig_verified":   _OIDC_SIG_VERIFIED,
        },
        "observers": sum(
            len(v) for v in request.app.state.observer_registry.values()
        ),
        "ws_clients": len(request.app.state.ws_clients),
    }


# ---------------------------------------------------------------------------
# Runtime simulation endpoints
# ---------------------------------------------------------------------------

@app.get("/frame", tags=["simulation"])
async def get_frame(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    return engine.current_frame()


@app.get("/scene", tags=["simulation"])
async def get_scene(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    return engine.current_scene()


@app.get("/frame/lookahead", tags=["simulation"])
async def get_lookahead(
    request: Request,
    steps: int = 3,
    auth: dict = Depends(get_auth),
):
    """Ghost lookahead: shadow-simulate N steps and return the projected scene."""
    import asyncio
    engine = get_engine(request)
    scene = await asyncio.to_thread(engine.lookahead, steps)
    return {"lookahead_steps": steps, "scene": scene}


@app.get("/report", tags=["simulation"])
async def get_report(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    return engine.current_report()


@app.get("/controls", tags=["simulation"])
async def get_controls(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    return engine.get_controls()


@app.post("/controls", tags=["simulation"])
async def set_controls(request: Request, auth: dict = Depends(get_auth)):
    body = await request.json()
    engine = get_engine(request)
    engine.set_controls(body)
    return {"status": "ok", "controls": engine.get_controls()}


@app.post("/pause", tags=["simulation"])
async def pause_sim(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    engine.pause()
    return {"status": "paused"}


@app.post("/resume", tags=["simulation"])
async def resume_sim(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    engine.resume()
    return {"status": "running"}


@app.post("/step", tags=["simulation"])
async def step_sim(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    engine.step_once()
    return engine.current_frame()


@app.post("/run_once", tags=["simulation"])
async def run_once(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    engine.run_once()
    return engine.current_frame()


@app.post("/snapshot", tags=["simulation"])
async def snapshot(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    snap = engine.snapshot()
    return {"status": "ok", "snapshot": snap}


# ---------------------------------------------------------------------------
# Nexus — programmatic data injection
# ---------------------------------------------------------------------------

@app.post("/nexus/inflow", tags=["nexus"])
async def nexus_inflow(request: Request, auth: dict = Depends(get_auth)):
    """
    Inject data points directly into the running simulation.

    Accepts a JSON body with one of:
      { "points": [{"x": 0.5, "y": 0.3, "energy": 1.0, "kind": "neutral"}, ...] }
      { "csv": "<raw CSV string with x,y columns>" }
      { "text": "free-text description" }  — hashes into deterministic coordinates

    Returns the number of points injected and the new frame state.
    """
    from geolatent.simulator import DataPoint
    engine = get_engine(request)
    body = await request.json()
    injected = 0

    if "points" in body:
        for p in body["points"]:
            try:
                engine.state.active.append(DataPoint(
                    x=float(p.get("x", 0.5)),
                    y=float(p.get("y", 0.5)),
                    energy=float(p.get("energy", 1.0)),
                    kind=str(p.get("kind", "neutral")),
                    variance=float(p.get("variance", 0.0)),
                ))
                injected += 1
            except (TypeError, ValueError):
                pass

    elif "csv" in body:
        try:
            from geolatent.adapters import from_csv_bytes
            pts = from_csv_bytes(body["csv"].encode())
            for pt in pts:
                engine.state.active.append(pt)
            injected = len(pts)
        except Exception as exc:
            raise HTTPException(400, f"CSV parse error: {exc}")

    elif "text" in body:
        import hashlib as _hl
        text = str(body["text"])
        h = _hl.sha256(text.encode()).digest()
        n = body.get("n", max(1, len(text) // 20))
        for i in range(n):
            seed = _hl.sha256(h + i.to_bytes(4, "big")).digest()
            engine.state.active.append(DataPoint(
                x=seed[0] / 255,
                y=seed[1] / 255,
                energy=0.5 + seed[2] / 510,
                kind="neutral",
            ))
        injected = n

    else:
        raise HTTPException(400, "Body must contain 'points', 'csv', or 'text'.")

    engine._refresh()
    return {"injected": injected, "active": len(engine.state.active), "frame": engine.current_frame()}


@app.get("/nexus/schema", tags=["nexus"])
async def nexus_schema():
    """Runtime contract for external integrations."""
    return {
        "version":    "3.0.0",
        "inflow":     "POST /nexus/inflow",
        "frame":      "GET /frame",
        "scene":      "GET /scene",
        "controls":   "GET|POST /controls",
        "websocket":  "/ws",
        "auth": {
            "jwt":        "POST /auth/login  (requires DATABASE_URL)",
            "dev_token":  "POST /auth/dev-token  (requires GEOLATENT_ALLOW_HEADER_DEV=true)",
            "dev_headers":"X-Tenant-Id + X-Principal-Id  (requires GEOLATENT_ALLOW_HEADER_DEV=true)",
        },
        "inflow_modes": ["neutral", "prey", "predator", "neutral_to_predatory", "finance_predator_prey"],
    }


# ---------------------------------------------------------------------------
# WebSocket — real-time stream
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def ws_stream(websocket: WebSocket):
    """
    Ephemeral WebSocket with 30-second JWT challenge.
    Streams frame/scene updates to connected observers.
    """
    from geolatent.auth import validate_ws_token
    await websocket.accept()

    # Challenge-response handshake
    challenge = str(uuid.uuid4())
    await websocket.send_json({"type": "challenge", "token": challenge})
    try:
        msg = await websocket.receive_json()
    except Exception:
        await websocket.close(4001)
        return

    auth = validate_ws_token(msg.get("token", ""), challenge)
    if not auth:
        await websocket.send_json({"type": "error", "detail": "auth_failed"})
        await websocket.close(4001)
        return

    await websocket.send_json({"type": "auth_ok"})
    websocket.app.state.ws_clients.add(websocket)

    # Register observer beam
    tenant_id  = auth.get("tenant_id", "anon")
    principal  = auth.get("principal_id", "anon")
    registry   = websocket.app.state.observer_registry
    registry.setdefault(tenant_id, {})[principal] = {
        "x": 0.5, "y": 0.5, "radius": 0.1, "ts": time.time()
    }

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            # Observer beam position update
            if data.get("type") == "observer":
                entry = registry.setdefault(tenant_id, {})
                entry[principal] = {
                    "x": float(data.get("x", 0.5)),
                    "y": float(data.get("y", 0.5)),
                    "radius": float(data.get("radius", 0.1)),
                    "ts": time.time(),
                }
                # Prune stale beams (older than 60 s)
                now = time.time()
                entry = {k: v for k, v in entry.items() if now - v["ts"] < 60}
                registry[tenant_id] = entry

                engine = websocket.app.state.engine
                if engine:
                    engine.set_observer(
                        float(data.get("x", 0.5)),
                        float(data.get("y", 0.5)),
                        float(data.get("radius", 0.1)),
                    )
                    await websocket.send_json({
                        "type": "frame",
                        "data": engine.current_frame(),
                    })
    finally:
        websocket.app.state.ws_clients.discard(websocket)
        registry.get(tenant_id, {}).pop(principal, None)


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/dev-token", tags=["auth"])
async def auth_dev_token(request: Request):
    """
    Issue a signed JWT for local development without a database.
    Only available when GEOLATENT_ALLOW_HEADER_DEV=true.
    """
    from geolatent.auth import ALLOW_DEV_HDR, issue_jwt
    if not ALLOW_DEV_HDR:
        raise HTTPException(403, "Dev tokens are disabled. Set GEOLATENT_ALLOW_HEADER_DEV=true.")
    body = await request.json()
    claims = {
        "tenant_id":    body.get("tenant_id", "dev-tenant"),
        "principal_id": body.get("principal_id", "dev-user"),
        "role":         body.get("role", "admin"),
        "email":        body.get("email", "dev@example.com"),
        "dev":          True,
    }
    return {"token": issue_jwt(claims), "note": "Dev token — do not use in production."}


@app.post("/auth/bootstrap", tags=["auth"])
async def auth_bootstrap(request: Request, pool=Depends(get_pool_optional)):
    from geolatent.auth import bootstrap_admin
    if pool is None:
        raise HTTPException(
            503,
            "Database not available. Use POST /auth/dev-token for a no-DB development token."
        )
    body = await request.json()
    async with pool.connection() as conn:
        token = await bootstrap_admin(conn, body)
    return {"token": token}


@app.post("/auth/login", tags=["auth"])
async def auth_login(request: Request, pool=Depends(get_pool_optional)):
    from geolatent.auth import login_user
    if pool is None:
        raise HTTPException(
            503,
            "Database not available. Use POST /auth/dev-token for a no-DB development token."
        )
    body = await request.json()
    async with pool.connection() as conn:
        token = await login_user(conn, body)
    return {"token": token}


@app.get("/auth/me", tags=["auth"])
async def auth_me(auth: dict = Depends(get_auth)):
    return auth


@app.get("/auth/invitations", tags=["auth"])
async def list_invitations(request: Request, auth: dict = Depends(get_auth), pool=Depends(get_pool_optional)):
    if pool is None:
        return []
    from geolatent.auth import get_invitations
    async with pool.connection() as conn:
        return await get_invitations(conn, auth["tenant_id"])


@app.post("/auth/invitations", tags=["auth"])
async def create_invitation(request: Request, auth: dict = Depends(get_auth), pool=Depends(get_pool)):
    from geolatent.auth import create_invitation as _create
    body = await request.json()
    async with pool.connection() as conn:
        return await _create(conn, auth, body)


@app.post("/auth/invitations/accept", tags=["auth"])
async def accept_invitation(request: Request, pool=Depends(get_pool)):
    from geolatent.auth import accept_invitation as _accept
    body = await request.json()
    async with pool.connection() as conn:
        token = await _accept(conn, body)
    return {"token": token}


# ---------------------------------------------------------------------------
# Workspace SaaS endpoints
# ---------------------------------------------------------------------------

_NO_DB_HINT = {"_note": "Database not configured — set DATABASE_URL in .env for persistence."}


@app.get("/workspace/dashboard", tags=["workspace"])
async def ws_dashboard(auth: dict = Depends(get_auth), pool=Depends(get_pool_optional)):
    if pool is None:
        return {**_NO_DB_HINT, "projects": 0, "datasets": 0, "runs": 0}
    from geolatent.persistence_db import get_dashboard
    async with pool.connection() as conn:
        return await get_dashboard(conn, auth["tenant_id"])


@app.get("/workspace/projects", tags=["workspace"])
async def list_projects(auth: dict = Depends(get_auth), pool=Depends(get_pool_optional)):
    if pool is None:
        return []
    from geolatent.persistence_db import list_projects as _list
    async with pool.connection() as conn:
        return await _list(conn, auth["tenant_id"])


@app.post("/workspace/projects", tags=["workspace"])
async def create_project(request: Request, auth: dict = Depends(get_auth), pool=Depends(get_pool)):
    from geolatent.persistence_db import create_project as _create
    body = await request.json()
    async with pool.connection() as conn:
        return await _create(conn, auth, body)


@app.post("/workspace/projects/{project_id}/share", tags=["workspace"])
async def share_project(project_id: str, request: Request, auth: dict = Depends(get_auth), pool=Depends(get_pool)):
    from geolatent.persistence_db import share_project as _share
    body = await request.json()
    async with pool.connection() as conn:
        return await _share(conn, auth, project_id, body)


@app.get("/workspace/datasets", tags=["workspace"])
async def list_datasets(auth: dict = Depends(get_auth), pool=Depends(get_pool_optional)):
    if pool is None:
        return []
    from geolatent.persistence_db import list_datasets as _list
    async with pool.connection() as conn:
        return await _list(conn, auth["tenant_id"])


@app.post("/workspace/datasets/upload", tags=["workspace"])
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    auth: dict = Depends(get_auth),
    pool=Depends(get_pool_optional),
):
    if pool is None:
        # In dev mode: parse CSV and inject directly into the running engine
        engine = request.app.state.engine
        if engine is None:
            raise HTTPException(503, "No database and no engine loaded — cannot ingest dataset.")
        content = await file.read()
        try:
            from geolatent.adapters import from_csv_bytes
            points = from_csv_bytes(content)
            for pt in points:
                engine.state.active.append(pt)
            engine._refresh()
        except Exception as exc:
            raise HTTPException(400, f"Failed to parse dataset: {exc}")
        return {
            "id":       None,
            "filename": file.filename,
            "points":   len(points),
            "_note":    "Injected directly into the running engine (no DB). Set DATABASE_URL to persist.",
        }
    from geolatent.persistence_db import save_dataset
    content = await file.read()
    async with pool.connection() as conn:
        record = await save_dataset(conn, auth, file.filename or "upload", content)
    return record


@app.get("/workspace/runs", tags=["workspace"])
async def list_runs(auth: dict = Depends(get_auth), pool=Depends(get_pool_optional)):
    if pool is None:
        return []
    from geolatent.persistence_db import list_runs as _list
    async with pool.connection() as conn:
        return await _list(conn, auth["tenant_id"])


@app.post("/workspace/runs", tags=["workspace"])
async def create_run(request: Request, auth: dict = Depends(get_auth), pool=Depends(get_pool)):
    from geolatent.persistence_db import create_run as _create
    body = await request.json()
    async with pool.connection() as conn:
        return await _create(conn, auth, body)


@app.post("/workspace/comparisons", tags=["workspace"])
async def compare_runs(request: Request, auth: dict = Depends(get_auth), pool=Depends(get_pool)):
    from geolatent.persistence_db import compare_runs as _compare
    body = await request.json()
    async with pool.connection() as conn:
        return await _compare(conn, auth["tenant_id"], body.get("run_ids", []))


@app.get("/workspace/access", tags=["workspace"])
async def get_access(auth: dict = Depends(get_auth), pool=Depends(get_pool_optional)):
    if pool is None:
        return []
    from geolatent.persistence_db import get_access_log
    async with pool.connection() as conn:
        return await get_access_log(conn, auth["tenant_id"])


@app.post("/workspace/runs/{run_id}/bundle", tags=["workspace"])
async def export_bundle(run_id: str, request: Request, auth: dict = Depends(get_auth), pool=Depends(get_pool)):
    from geolatent.persistence_db import create_repro_bundle
    async with pool.connection() as conn:
        bundle = await create_repro_bundle(conn, auth, run_id)
    return bundle


# ---------------------------------------------------------------------------
# Reproducibility bundles
# ---------------------------------------------------------------------------

@app.post("/bundles/repro", tags=["bundles"])
async def create_bundle(request: Request, auth: dict = Depends(get_auth)):
    engine = get_engine(request)
    bundle_secret = os.environ.get("GEOLATENT_BUNDLE_SECRET", "changeme")
    payload = {
        "step":      engine.current_frame().get("step"),
        "frame":     engine.current_frame(),
        "scene":     engine.current_scene(),
        "report":    engine.current_report(),
        "tenant_id": auth.get("tenant_id"),
        "actor":     auth.get("principal_id"),
        "ts":        time.time(),
    }
    body = json.dumps(payload, sort_keys=True).encode()
    sig = hmac.new(bundle_secret.encode(), body, hashlib.sha256).hexdigest()
    return {"payload": payload, "signature": sig}


@app.get("/bundles/repro/verify", tags=["bundles"])
async def verify_bundle(bundle_path: str):
    bundle_secret = os.environ.get("GEOLATENT_BUNDLE_SECRET", "changeme")
    import pathlib
    p = pathlib.Path(bundle_path)
    if not p.exists():
        raise HTTPException(404, "Bundle not found")
    data = json.loads(p.read_text())
    body = json.dumps(data.get("payload", {}), sort_keys=True).encode()
    expected = hmac.new(bundle_secret.encode(), body, hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(expected, data.get("signature", ""))
    return {"valid": ok, "bundle_path": bundle_path}


# ---------------------------------------------------------------------------
# Narrative packs
# ---------------------------------------------------------------------------

_NARRATIVE_PACKS: dict[str, dict] = {
    "data-earthquake": {
        "id": "data-earthquake",
        "title": "Data Earthquake",
        "description": "A sudden anomaly cascade triggers tectonic collapse of a stable baseline.",
        "steps": [
            {"step": 1, "label": "Stable plateau", "controls": {"variance": 0.1}},
            {"step": 3, "label": "First tremor",   "controls": {"variance": 0.4}},
            {"step": 6, "label": "Cascade begins", "controls": {"variance": 0.8}},
            {"step": 9, "label": "Collapse",       "controls": {"variance": 1.2}},
        ],
    },
    "neutral-baseline": {
        "id": "neutral-baseline",
        "title": "Neutral Baseline",
        "description": "Calibrate terrain physics with a balanced neutral inflow before introducing adversarial data.",
        "steps": [
            {"step": 1, "label": "Genesis",      "controls": {"inflow_mode": "neutral"}},
            {"step": 5, "label": "Stabilise",    "controls": {"inflow_mode": "neutral"}},
            {"step": 10, "label": "Steady state", "controls": {}},
        ],
    },
    "predator-prey": {
        "id": "predator-prey",
        "title": "Predator–Prey Collision",
        "description": "Two adversarial datasets compete for terrain dominance via Lotka–Volterra dynamics.",
        "steps": [
            {"step": 1, "label": "Prey establishes",  "controls": {"inflow_mode": "prey"}},
            {"step": 4, "label": "Predator enters",   "controls": {"inflow_mode": "predator"}},
            {"step": 8, "label": "Peak competition",  "controls": {}},
            {"step": 14, "label": "Equilibrium",      "controls": {}},
        ],
    },
    "planetarium-show": {
        "id": "planetarium-show",
        "title": "Data Planetarium",
        "description": "Live public-dataset tour guided for non-technical museum audiences.",
        "steps": [
            {"step": 1,  "label": "World seed loads",     "controls": {"inflow_mode": "neutral"}},
            {"step": 3,  "label": "Biomes emerge",        "controls": {}},
            {"step": 7,  "label": "First anomaly canyon", "controls": {"inject_anomaly": True}},
            {"step": 12, "label": "Homeostasis restores", "controls": {}},
            {"step": 16, "label": "Fossil record",        "controls": {}},
        ],
    },
    "fraud-aml": {
        "id": "fraud-aml",
        "title": "Fraud / AML Terrain",
        "description": "Financial transaction data — predator sinkholes become risk explainability.",
        "steps": [
            {"step": 1,  "label": "Baseline transactions", "controls": {"inflow_mode": "neutral"}},
            {"step": 5,  "label": "Fraud cluster emerges", "controls": {"inflow_mode": "predator"}},
            {"step": 9,  "label": "AML alert fired",       "controls": {}},
            {"step": 13, "label": "Intervention + remediation", "controls": {}},
        ],
    },
}


@app.get("/narratives", tags=["narratives"])
async def list_narratives():
    return [{"id": v["id"], "title": v["title"], "description": v["description"]}
            for v in _NARRATIVE_PACKS.values()]


@app.get("/narratives/{pack_id}", tags=["narratives"])
async def get_narrative(pack_id: str):
    pack = _NARRATIVE_PACKS.get(pack_id)
    if not pack:
        raise HTTPException(404, f"Narrative pack '{pack_id}' not found")
    return pack


# ---------------------------------------------------------------------------
# SDK endpoints
# ---------------------------------------------------------------------------

@app.get("/sdk/schema", tags=["sdk"])
async def sdk_schema(request: Request):
    """Runtime contract for external integrations (Unity/Unreal/Godot)."""
    return {
        "version": "3.0.0",
        "websocket": "/ws",
        "endpoints": {
            "frame":   "GET /frame",
            "scene":   "GET /scene",
            "report":  "GET /report",
            "controls":"GET|POST /controls",
            "exports": "GET /sdk/exports/latest",
        },
        "scene_fields":  ["grid_w", "grid_h", "vertices", "faces", "biomes", "entities"],
        "frame_fields":  ["step", "terrain", "sea_level", "metrics", "interventions"],
        "auth": "Bearer JWT — POST /auth/login",
    }


@app.get("/sdk/exports/latest", tags=["sdk"])
async def sdk_exports(request: Request, auth: dict = Depends(get_auth)):
    """
    Current scene/frame/control payload for external engines.
    Suitable for polling by VR/AR middleware on a 100 ms interval.
    """
    engine = get_engine(request)
    return {
        "frame":    engine.current_frame(),
        "scene":    engine.current_scene(),
        "controls": engine.get_controls(),
        "ts":       time.time(),
    }


# ---------------------------------------------------------------------------
# Static viewer (Three.js / HTML client served from docs/viewer/)
# ---------------------------------------------------------------------------

_viewer_path = os.path.join(os.path.dirname(__file__), "..", "docs", "viewer")
if os.path.isdir(_viewer_path):
    app.mount("/static", StaticFiles(directory=_viewer_path), name="static")


@app.get("/", response_class=HTMLResponse, tags=["viewer"], include_in_schema=False)
async def serve_viewer():
    index = os.path.join(_viewer_path, "index.html")
    if os.path.exists(index):
        with open(index) as f:
            return HTMLResponse(f.read())
    return HTMLResponse("""
<!DOCTYPE html><html><head><title>Geo-latent v3.0</title></head><body>
<h1>Geo-latent Observatory v3.0</h1>
<p>API docs: <a href="/docs">/docs</a></p>
<p>Start a simulation: <code>python3 -m geolatent serve --scenario neutral_baseline --steps 20</code></p>
</body></html>
""")


# ---------------------------------------------------------------------------
# Include market expansion routers (added after core app is fully configured)
# ---------------------------------------------------------------------------
# These are imported last to avoid circular imports at module load time.

def _include_expansion_routers():
    try:
        from geolatent.gaming    import router as gaming_router
        app.include_router(gaming_router,    prefix="/gaming",    tags=["gaming"])
    except ImportError:
        pass
    try:
        from geolatent.education import router as education_router
        app.include_router(education_router, prefix="/education", tags=["education"])
    except ImportError:
        pass
    try:
        from geolatent.billing   import router as billing_router
        app.include_router(billing_router,   prefix="/billing",   tags=["billing"])
    except ImportError:
        pass
    try:
        from geolatent.biome_lore import router as biome_router
        app.include_router(biome_router,     prefix="/biomes",    tags=["biomes"])
    except ImportError:
        pass
    try:
        from geolatent.cael import router as cael_router
        app.include_router(cael_router, prefix="/cael", tags=["cael"])
    except ImportError:
        pass
    try:
        from geolatent.performance import router as perf_router
        app.include_router(perf_router, prefix="/performance", tags=["performance"])
    except ImportError:
        pass


_include_expansion_routers()
