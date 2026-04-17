"""
geolatent/persistence_db.py
PostgreSQL persistence layer.

KEY FIX: All public functions now accept an explicit `conn` parameter
         (provided by the caller from app.state.db_pool).
         There is NO per-request _connect() call anywhere in this file.
"""
from __future__ import annotations

import json
import time
import uuid
import hashlib
import os
from typing import Any


# ---------------------------------------------------------------------------
# Schema bootstrap (called once in lifespan, not per-request)
# ---------------------------------------------------------------------------

async def init_schema(conn) -> None:
    """
    Idempotent schema creation.
    In production, replace this with `alembic upgrade head` in the
    container entrypoint — see alembic/ directory.
    """
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            created_at  DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS principals (
            id          TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email       TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'viewer',
            pw_hash     TEXT,
            created_at  DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
            UNIQUE(tenant_id, email)
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS invitations (
            token       TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            email       TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'viewer',
            created_at  DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
            accepted    BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id          TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            shared_with JSONB NOT NULL DEFAULT '[]',
            created_at  DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS datasets (
            id          TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            filename    TEXT NOT NULL,
            size_bytes  INTEGER NOT NULL,
            sha256      TEXT NOT NULL,
            created_at  DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id           TEXT PRIMARY KEY,
            tenant_id    TEXT NOT NULL,
            project_id   TEXT,
            scenario     TEXT,
            dataset_id   TEXT,
            steps        INTEGER,
            status       TEXT NOT NULL DEFAULT 'pending',
            result       JSONB,
            created_at   DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW()),
            finished_at  DOUBLE PRECISION
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS simulation_frames (
            id          BIGSERIAL PRIMARY KEY,
            run_id      TEXT NOT NULL,
            tenant_id   TEXT NOT NULL,
            step        INTEGER NOT NULL,
            frame       JSONB NOT NULL,
            ts          DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          BIGSERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            actor_id    TEXT,
            action      TEXT NOT NULL,
            resource    TEXT,
            detail      JSONB,
            ts          DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS immortal_cells (
            id          TEXT PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            run_id      TEXT NOT NULL,
            grid_x      INTEGER NOT NULL,
            grid_y      INTEGER NOT NULL,
            first_seen  INTEGER NOT NULL,
            tick_count  INTEGER NOT NULL DEFAULT 1,
            density     DOUBLE PRECISION,
            biome_label TEXT,
            etched_at   DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS billing_usage (
            id          BIGSERIAL PRIMARY KEY,
            tenant_id   TEXT NOT NULL,
            metric      TEXT NOT NULL,
            quantity    DOUBLE PRECISION NOT NULL,
            ts          DOUBLE PRECISION NOT NULL DEFAULT EXTRACT(EPOCH FROM NOW())
        )
    """)
    await conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_frames_run   ON simulation_frames(run_id, step);
        CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_cells_tenant ON immortal_cells(tenant_id, run_id);
        CREATE INDEX IF NOT EXISTS idx_billing_t    ON billing_usage(tenant_id, ts DESC);
    """)


# ---------------------------------------------------------------------------
# Audit helper (called throughout this module)
# ---------------------------------------------------------------------------

async def _audit(conn, tenant_id: str, actor_id: str | None, action: str,
                 resource: str | None = None, detail: Any = None) -> None:
    await conn.execute(
        "INSERT INTO audit_log (tenant_id, actor_id, action, resource, detail, ts) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (tenant_id, actor_id, action, resource, json.dumps(detail), time.time()),
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

async def get_dashboard(conn, tenant_id: str) -> dict:
    proj_count = (await (await conn.execute(
        "SELECT COUNT(*) FROM projects WHERE tenant_id=%s", (tenant_id,)
    )).fetchone())[0]
    run_count = (await (await conn.execute(
        "SELECT COUNT(*) FROM runs WHERE tenant_id=%s", (tenant_id,)
    )).fetchone())[0]
    dataset_count = (await (await conn.execute(
        "SELECT COUNT(*) FROM datasets WHERE tenant_id=%s", (tenant_id,)
    )).fetchone())[0]
    return {
        "tenant_id":    tenant_id,
        "projects":     proj_count,
        "runs":         run_count,
        "datasets":     dataset_count,
    }


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

async def list_projects(conn, tenant_id: str) -> list:
    rows = await (await conn.execute(
        "SELECT id, name, description, created_at FROM projects WHERE tenant_id=%s ORDER BY created_at DESC",
        (tenant_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def create_project(conn, auth: dict, body: dict) -> dict:
    pid = str(uuid.uuid4())
    now = time.time()
    await conn.execute(
        "INSERT INTO projects (id, tenant_id, name, description, created_at) VALUES (%s,%s,%s,%s,%s)",
        (pid, auth["tenant_id"], body.get("name", "Untitled"), body.get("description", ""), now),
    )
    await _audit(conn, auth["tenant_id"], auth.get("principal_id"), "project.create", pid)
    return {"id": pid, "name": body.get("name", "Untitled"), "created_at": now}


async def share_project(conn, auth: dict, project_id: str, body: dict) -> dict:
    share_with = body.get("principal_ids", [])
    await conn.execute(
        "UPDATE projects SET shared_with=%s WHERE id=%s AND tenant_id=%s",
        (json.dumps(share_with), project_id, auth["tenant_id"]),
    )
    await _audit(conn, auth["tenant_id"], auth.get("principal_id"),
                 "project.share", project_id, {"shared_with": share_with})
    return {"status": "ok", "project_id": project_id, "shared_with": share_with}


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

async def list_datasets(conn, tenant_id: str) -> list:
    rows = await (await conn.execute(
        "SELECT id, filename, size_bytes, sha256, created_at FROM datasets "
        "WHERE tenant_id=%s ORDER BY created_at DESC",
        (tenant_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def save_dataset(conn, auth: dict, filename: str, content: bytes) -> dict:
    did = str(uuid.uuid4())
    sha = hashlib.sha256(content).hexdigest()
    now = time.time()
    await conn.execute(
        "INSERT INTO datasets (id, tenant_id, filename, size_bytes, sha256, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s)",
        (did, auth["tenant_id"], filename, len(content), sha, now),
    )
    await _audit(conn, auth["tenant_id"], auth.get("principal_id"),
                 "dataset.upload", did, {"filename": filename, "sha256": sha})
    return {"id": did, "filename": filename, "size_bytes": len(content),
            "sha256": sha, "created_at": now}


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

async def list_runs(conn, tenant_id: str) -> list:
    rows = await (await conn.execute(
        "SELECT id, project_id, scenario, steps, status, created_at, finished_at "
        "FROM runs WHERE tenant_id=%s ORDER BY created_at DESC",
        (tenant_id,),
    )).fetchall()
    return [dict(r) for r in rows]


async def create_run(conn, auth: dict, body: dict) -> dict:
    rid = str(uuid.uuid4())
    now = time.time()
    await conn.execute(
        "INSERT INTO runs (id, tenant_id, project_id, scenario, dataset_id, steps, status, created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,'pending',%s)",
        (rid, auth["tenant_id"], body.get("project_id"),
         body.get("scenario"), body.get("dataset_id"), body.get("steps", 10), now),
    )
    await _audit(conn, auth["tenant_id"], auth.get("principal_id"), "run.create", rid, body)
    return {"id": rid, "status": "pending", "created_at": now}


async def compare_runs(conn, tenant_id: str, run_ids: list) -> dict:
    if not run_ids:
        return {"error": "No run IDs provided"}
    placeholders = ",".join(["%s"] * len(run_ids))
    rows = await (await conn.execute(
        f"SELECT id, scenario, steps, status, result FROM runs "
        f"WHERE tenant_id=%s AND id IN ({placeholders})",
        [tenant_id] + run_ids,
    )).fetchall()
    return {"runs": [dict(r) for r in rows], "compared_at": time.time()}


# ---------------------------------------------------------------------------
# Access log
# ---------------------------------------------------------------------------

async def get_access_log(conn, tenant_id: str) -> list:
    rows = await (await conn.execute(
        "SELECT actor_id, action, resource, ts FROM audit_log "
        "WHERE tenant_id=%s ORDER BY ts DESC LIMIT 200",
        (tenant_id,),
    )).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Reproducibility bundle
# ---------------------------------------------------------------------------

async def create_repro_bundle(conn, auth: dict, run_id: str) -> dict:
    import hmac as _hmac, hashlib as _hashlib
    secret = os.environ.get("GEOLATENT_BUNDLE_SECRET", "changeme")
    row = await (await conn.execute(
        "SELECT * FROM runs WHERE id=%s AND tenant_id=%s",
        (run_id, auth["tenant_id"]),
    )).fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Run not found")
    payload = {
        "run_id":    run_id,
        "tenant_id": auth["tenant_id"],
        "actor":     auth.get("principal_id"),
        "run":       dict(row),
        "ts":        time.time(),
    }
    body = json.dumps(payload, sort_keys=True).encode()
    sig = _hmac.new(secret.encode(), body, _hashlib.sha256).hexdigest()
    await _audit(conn, auth["tenant_id"], auth.get("principal_id"),
                 "bundle.export", run_id)
    return {"payload": payload, "signature": sig}


# ---------------------------------------------------------------------------
# Immortal cell tracking
# ---------------------------------------------------------------------------

async def upsert_immortal_cell(conn, tenant_id: str, run_id: str,
                                gx: int, gy: int, density: float,
                                biome_label: str) -> None:
    cell_id = f"{tenant_id}:{run_id}:{gx}:{gy}"
    await conn.execute("""
        INSERT INTO immortal_cells (id, tenant_id, run_id, grid_x, grid_y,
                                    first_seen, tick_count, density, biome_label)
        VALUES (%s,%s,%s,%s,%s,0,1,%s,%s)
        ON CONFLICT (id) DO UPDATE
            SET tick_count  = immortal_cells.tick_count + 1,
                density     = EXCLUDED.density,
                biome_label = EXCLUDED.biome_label
    """, (cell_id, tenant_id, run_id, gx, gy, density, biome_label))


async def get_immortal_cells(conn, tenant_id: str, run_id: str) -> list:
    rows = await (await conn.execute(
        "SELECT grid_x, grid_y, tick_count, density, biome_label "
        "FROM immortal_cells WHERE tenant_id=%s AND run_id=%s "
        "AND tick_count >= 2000 ORDER BY tick_count DESC",
        (tenant_id, run_id),
    )).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Frame persistence
# ---------------------------------------------------------------------------

async def save_frame(conn, run_id: str, tenant_id: str, step: int, frame: dict) -> None:
    await conn.execute(
        "INSERT INTO simulation_frames (run_id, tenant_id, step, frame, ts) VALUES (%s,%s,%s,%s,%s)",
        (run_id, tenant_id, step, json.dumps(frame), time.time()),
    )


async def load_frames(conn, run_id: str, tenant_id: str) -> list:
    rows = await (await conn.execute(
        "SELECT step, frame FROM simulation_frames WHERE run_id=%s AND tenant_id=%s ORDER BY step",
        (run_id, tenant_id),
    )).fetchall()
    return [{"step": r[0], "frame": r[1]} for r in rows]


# ---------------------------------------------------------------------------
# Billing usage
# ---------------------------------------------------------------------------

async def record_usage(conn, tenant_id: str, metric: str, quantity: float) -> None:
    await conn.execute(
        "INSERT INTO billing_usage (tenant_id, metric, quantity, ts) VALUES (%s,%s,%s,%s)",
        (tenant_id, metric, quantity, time.time()),
    )


async def get_usage_summary(conn, tenant_id: str, since: float | None = None) -> dict:
    since = since or (time.time() - 86400 * 30)
    rows = await (await conn.execute(
        "SELECT metric, SUM(quantity) as total FROM billing_usage "
        "WHERE tenant_id=%s AND ts>=%s GROUP BY metric",
        (tenant_id, since),
    )).fetchall()
    return {r[0]: float(r[1]) for r in rows}
