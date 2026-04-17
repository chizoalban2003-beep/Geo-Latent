# GitHub Copilot Instructions — Geo-latent v3.0

This file teaches Copilot the conventions, architecture, and rules of this codebase.
Follow every section when suggesting code, writing tests, or answering questions.

---

## What this project is

Geo-latent is a SaaS platform that transforms any structured dataset into an interactive
3-D terrain simulation. High-density data regions become mountains; anomalies invert into
glowing canyons; two competing datasets fight for terrain dominance via Lotka-Volterra
predator-prey dynamics.

---

## Stack

| Layer | Technology |
|-------|-----------|
| API   | FastAPI 0.111+ with `@asynccontextmanager` lifespan — **never** `@app.on_event` |
| DB    | PostgreSQL via `psycopg[async]` + `psycopg-pool` `AsyncConnectionPool` |
| Migrations | Alembic — **never** raw `CREATE TABLE IF NOT EXISTS` in application code |
| Physics | numpy-vectorized KDE — **never** pure-Python nested loops over the grid |
| Auth  | HS256 JWT (app-issued) + RS256/OIDC JWKS (Clerk/Auth0) via `geolatent/auth.py` |
| Frontend | Three.js served from `docs/viewer/index.html` at `/` |
| Testing | pytest with lifespan mocked via `conftest.py` — no real DB needed |

---

## Project layout

```
geolatent/
  api.py              All FastAPI endpoints + lifespan. Import routers at the bottom.
  server.py           ASGI entrypoint: uvicorn geolatent.server:app
  engine.py           GeolatentEngine — single object the API talks to via app.state
  simulator.py        WorldState, DataPoint, KDE (numpy), water cycle, Lotka-Volterra
  scenarios.py        Inflow generators: neutral / prey / predator / finance
  adapters.py         CSV/JSONL → DataPoint. Always strip __proto__/constructor/prototype.
  mesh.py             build_scene() → {vertices, faces, biomes, entities} for Three.js
  metrics.py          compute_report() → Stability Index, entropy, drift, bias
  policy.py           PolicyAgent — EMA-smoothed homeostasis. step_value = state.step or 0
  auth.py             issue_jwt(), _verify_hs256(), RS256 OIDC path, workspace flows
  persistence.py      File-backed snapshot / replay (no DB required)
  persistence_db.py   All SQL. Functions take explicit conn= from AsyncConnectionPool.
  entities.py         Fossil, mist, beacon synthesis
  visualization.py    ASCII terminal renderer
  cli.py              python3 -m geolatent run|replay|serve
  demo.py             python3 -m geolatent.demo  (no server needed)
  gaming.py           /gaming/* router: Godot/Unity bridge, player registry, world seeds
  education.py        /education/* router: guided tours, worksheets, quiz generation
  billing.py          /billing/* router: Stripe tiers, tier gates, usage metering
  biome_lore.py       /biomes/* router: LLM biome descriptions (Claude API fallback)
  tests/test_all.py   38 tests — all five layers + market expansion modules
docs/viewer/
  index.html          Full Three.js 3-D viewer (terrain, HUD panels, controls)
alembic/              Database migrations (001_baseline.py covers all tables)
.github/
  copilot-instructions.md   ← this file
  workflows/ci.yml    pytest + syntax check on every push
```

---

## Architecture rules Copilot must follow

### 1. Lifespan — never @app.on_event

```python
# WRONG — deprecated in FastAPI 0.95+
@app.on_event("startup")
async def startup(): ...

# RIGHT
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown
app = FastAPI(lifespan=lifespan)
```

### 2. Database — always use the pool from app.state

```python
# WRONG — opens a new connection per request
async def route():
    conn = await psycopg.connect(DATABASE_URL)

# RIGHT — use the shared pool initialised in lifespan
async def route(request: Request):
    async with request.app.state.db_pool.connection() as conn:
        ...
```

### 3. persistence_db.py — all functions take explicit conn

```python
# WRONG
async def get_dashboard(tenant_id: str):
    conn = await _connect()   # ← never do this

# RIGHT
async def get_dashboard(conn, tenant_id: str):
    rows = await (await conn.execute("SELECT ...", (tenant_id,))).fetchall()
    return [dict(r) for r in rows]
```

### 4. KDE — always numpy, never Python loops over the grid

```python
# WRONG — O(W × H × N)
for r in range(ROWS):
    for c in range(COLS):
        for pt in state.active:
            terrain[r][c] += kernel(r, c, pt)

# RIGHT — O(N · σ²), only updates cells within ceil(3σ) of each point
# See simulator.synthesize_topology_numpy() for the reference implementation
```

### 5. Policy interventions — step is never None

```python
# WRONG
PolicyIntervention(step=step, ...)      # step can be None at tick 0

# RIGHT
step_value = state.step or 0
PolicyIntervention(step=step_value, ...)
```

### 6. Prototype pollution — always sanitise incoming JSON

```python
# Every function that touches user-supplied dicts must call:
from geolatent.adapters import _sanitise
clean = _sanitise(user_dict)
# _sanitise strips __proto__, constructor, prototype keys
```

### 7. Tier gates — check before serving premium features

```python
from geolatent.billing import require_gate
# At the top of any premium endpoint:
require_gate(auth["tenant_id"], "sdk_exports", tier_needed="studio")
```

### 8. Auth — always parse via parse_request_auth

```python
from geolatent.auth import parse_request_auth
# Use as a FastAPI dependency:
async def get_auth(request: Request) -> dict:
    return await parse_request_auth(request)
# Then in routes: auth: dict = Depends(get_auth)
```

### 9. New routers go in their own file and are included at the bottom of api.py

```python
# In geolatent/myfeature.py:
from fastapi import APIRouter
router = APIRouter()

@router.get("/something")
async def something(): ...

# In geolatent/api.py (bottom of file, inside _include_expansion_routers):
from geolatent.myfeature import router as myfeature_router
app.include_router(myfeature_router, prefix="/myfeature", tags=["myfeature"])
```

---

## Data model

```python
@dataclass
class DataPoint:
    x: float        # normalised [0, 1]
    y: float        # normalised [0, 1]
    energy: float   # magnitude (payload_value)
    kind: str       # neutral | prey | predator
    age: int        # ticks since inflow
    variance: float # volatility score

@dataclass
class WorldState:
    grid_w: int; grid_h: int
    active: list[DataPoint]      # live terrain contributors
    abyss:  list[DataPoint]      # stale, mutating
    atmosphere: list[DataPoint]  # evaporated, may recondense
    terrain: list[list[float]]   # [ROWS][COLS] height values
    sea_level: float             # carrying capacity threshold
    sigma: float                 # KDE bandwidth
    immortal_candidates: dict    # (gx, gy) → tick_count
```

---

## Ingestion API schema

Every dataset must be normalised to:

| Field | Type | Description |
|-------|------|-------------|
| `entity_id` | string | Object identifier |
| `timestamp` | int | Simulation tick |
| `payload_value` | float | Magnitude (mapped to `energy`) |
| `variance_score` | float | Volatility |
| `x`, `y` | float [0,1] | Spatial coordinates (auto-normalised if outside range) |
| `kind` | string | `neutral` / `prey` / `predator` |

---

## Biome naming convention

Always use the hybrid format: `"<Poetic Name> — <Statistical Signature>"`

Examples:
- `"The Whispering Shelf — Low-Variance Plateau"`
- `"The Fracture Bloom — High-Gradient Drift Zone"`
- `"The Crown of Noise — High-Variance Highlands"`
- `"The Null Fens — Sparse Anomaly Wetland"`

---

## Stability Index formula

```
S = ∫₀ᵀ InterventionROI(t) dt  /  TotalEntropyGenerated
```

- S ≥ 0.7 → "Stabilized Manifold"
- 0.4 ≤ S < 0.7 → "Transitional State"
- S < 0.4 → "Systemic Collapse"

---

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | yes | PostgreSQL connection string |
| `GEOLATENT_JWT_SECRET` | yes | HS256 signing key — rotate with `openssl rand -hex 32` |
| `GEOLATENT_AUDIT_SIGNING_KEY` | yes | Audit log signing |
| `GEOLATENT_BUNDLE_SECRET` | yes | Reproducibility bundle HMAC |
| `GEOLATENT_ALLOW_HEADER_DEV` | no | `false` in production, `true` for local dev only |
| `GEOLATENT_OIDC_JWKS_URI` | no | Clerk/Auth0/Cognito JWKS URL for RS256 |
| `STRIPE_SECRET_KEY` | no | Enables billing endpoints |
| `ANTHROPIC_API_KEY` | no | Enables LLM biome lore — falls back to procedural |
| `GEOLATENT_REDIS_URL` | no | Redis for pub/sub across WebSocket workers |

---

## Test conventions

- All tests live in `geolatent/tests/test_all.py`
- `conftest.py` provides `mock_pool`, `mock_engine`, and `test_env` fixtures
- Tests never need a real Postgres connection — use the mock pool from conftest
- Every new module needs at least: one happy-path test, one edge-case test
- Run with: `pytest geolatent/tests/ -v`

---

## Billing tier gates

| Gate key | Free | Research | Studio | Enterprise |
|----------|------|----------|--------|------------|
| `repro_bundles` | — | ✓ | ✓ | ✓ |
| `sdk_exports` | — | — | ✓ | ✓ |
| `gaming_ws` | — | — | ✓ | ✓ |
| `education_export` | — | ✓ | ✓ | ✓ |
| `biome_lore_llm` | — | ✓ | ✓ | ✓ |
| `oidc_sso` | — | — | — | ✓ |

Always call `require_gate(tenant_id, gate_name)` before serving gated features.

---

## WebSocket protocol

```
Client → Server:
  {"type": "challenge", "token": "<JWT>"}          auth response
  {"type": "observer", "x": 0.5, "y": 0.5, "radius": 0.1}  beam update
  {"type": "ping"}

Server → Client:
  {"type": "challenge", "token": "<challenge-string>"}  initial handshake
  {"type": "auth_ok"}
  {"type": "frame", "data": {...}}                 terrain update
  {"type": "error", "detail": "auth_failed"}
```

WebSocket tokens are ephemeral: 30-second TTL, `token_type=ws_challenge`.
Standard long-lived tokens are rejected on the WebSocket endpoint.

---

## Gaming integration

The observer beam is the player character mechanic:
- `POST /gaming/player_move` with `{x, y, radius}` moves the observer beam
- `WS /gaming/ws` runs a 50ms game loop for real-time play
- `GET /gaming/godot_schema` returns the GDScript integration snippet
- `GET /gaming/unity_schema` returns the C# polling snippet
- `GET /gaming/world_seed?dataset=gdelt` generates a world from a public dataset

---

## Do not do these things

- Never use `@app.on_event` — use lifespan
- Never open a database connection per-request — use `app.state.db_pool`
- Never write `CREATE TABLE IF NOT EXISTS` in application code — use Alembic
- Never iterate the full grid × all points in Python — use the numpy KDE path
- Never set `GEOLATENT_ALLOW_HEADER_DEV=true` in production
- Never hardcode secrets — all secrets come from environment variables
- Never skip `_sanitise()` on user-supplied JSON dicts
- Never use `step=step` in PolicyIntervention — use `step_value = state.step or 0`
- Never put prose or explanations inside the Three.js viewer HTML — keep it clean JS/CSS
