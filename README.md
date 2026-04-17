# Geo-latent v3.0 — Spatial Data-OS

> Transform any dataset into a navigable, self-regulating 3-D ecological simulation.

[![CI](https://github.com/chizoalban2003-beep/geo-latent/actions/workflows/ci.yml/badge.svg)](https://github.com/chizoalban2003-beep/geo-latent/actions)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## What it is

Geo-latent is a universal SaaS platform that ingests any structured dataset — financial transactions, genomic sequences, network logs, climate sensors, game events — and synthesises it into a continuous, interactive 3-D terrain using Kernel Density Estimation and ecological simulation physics.

High-density data clusters become mountain ranges. Anomalies invert into glowing gravity-well canyons. Two competing datasets fight for terrain dominance via Lotka-Volterra predator-prey dynamics. The system monitors its own entropy and applies homeostatic corrections. Every cell that remains stable for 2,000 consecutive ticks is etched into a TimescaleDB ledger as an **Immortal Cell** — a universal truth in your data.

The same engine powers:
- **Research SaaS** — fraud/AML terrain, genomics drift, cyber anomaly detection
- **Education** — guided KDE tours, student worksheets, quiz generation
- **Gaming** — Godot/Unity/Unreal integration, observer-as-player, multiplayer worlds
- **Entertainment** — live data planetarium, museum installations, procedural world generation

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 1 — Ingestion & Security Boundary                      │
│  REST/WS gateway · JWT auth · prototype pollution guards      │
│  multi-observer sync registry · ephemeral 30s WS tokens       │
├──────────────────────────────────────────────────────────────┤
│  Layer 2 — Core Physics & Mathematical Engine                 │
│  KDE geomorphology · gravity-well inversion · Lotka-Volterra  │
│  predator-prey terrain erosion · numpy-vectorized O(N·σ²)     │
├──────────────────────────────────────────────────────────────┤
│  Layer 3 — Autonomic Homeostasis                              │
│  Shannon entropy · entropy lightning · EMA policy agent        │
│  sea-level homeostasis · Gaussian pruning · carrying capacity  │
├──────────────────────────────────────────────────────────────┤
│  Layer 4 — Rendering & Sensory Frontend                       │
│  Three.js 3-D terrain · CAEL semantic log · biome lore (LLM)  │
│  procedural audio · ghost geometry · observer beams           │
├──────────────────────────────────────────────────────────────┤
│  Layer 5 — Post-Game Analytics & Temporal Ledger              │
│  Immortal cell tracking · Stability Index S = ∫ROI/Hdt        │
│  signed reproducibility bundles · TimescaleDB hypertable      │
└──────────────────────────────────────────────────────────────┘
```

### Biome naming

Every terrain region receives a hybrid scientific-poetic label:

| Biome | Statistical signature |
|---|---|
| The Whispering Shelf | Low-Variance Plateau |
| The Fracture Bloom | High-Gradient Drift Zone |
| The Tidal Archive | Seasonal Density Basin |
| The Crown of Noise | High-Variance Highlands |
| The Null Fens | Sparse Anomaly Wetland |
| The Shattering Meridian | Extreme Instability Ridge |
| The Deep Trench | Abyssal Low-Density Canyon |
| The Amber Steppe | Mid-Variance Transition Belt |

---

## Quick start

### Option A — Docker (recommended)

```bash
cp .env.example .env          # fill in real secrets
docker compose up --build     # starts app + Postgres + Redis
```

Open: `http://localhost:8000/`

### Option B — Local Python

```bash
pip install -r requirements.txt
alembic upgrade head           # create database tables
python3 -m geolatent serve --host 0.0.0.0 --port 8000 --scenario neutral_baseline --steps 20
```

Open: `http://localhost:8000/`

### Option C — CLI demo (no server needed)

```bash
pip install -r requirements.txt
python3 -m geolatent.demo      # ASCII terrain in terminal
python3 -m geolatent run --scenario finance_predator_prey --steps 14 --render
python3 -m geolatent run --csv data/events.csv --steps 8 --render
```

---

## Dataset ingestion

Drop any CSV or JSONL file on `POST /workspace/datasets/upload`.

**CSV schema** (columns are normalised to [0,1] automatically):

| Column | Required | Description |
|---|---|---|
| `x` | yes | Spatial X coordinate |
| `y` | yes | Spatial Y coordinate |
| `energy` | no | Magnitude / payload value |
| `kind` | no | `neutral` \| `prey` \| `predator` |
| `variance_score` | no | Volatility |

**JSONL schema** — one JSON object per line, same fields.

---

## API reference

Full interactive docs at `http://localhost:8000/docs`.

### Core simulation

```
GET  /health                    — engine + db + redis status
GET  /frame                     — current simulation frame
GET  /scene                     — 3-D mesh (vertices, faces, biomes)
GET  /report                    — stability index, drift, entropy
GET  /controls                  — current runtime controls
POST /controls                  — update controls
POST /pause | /resume | /step
WS   /ws                        — real-time stream (30s JWT challenge)
```

### Workspace SaaS

```
POST /auth/bootstrap            — one-time admin setup
POST /auth/login                — issue JWT
GET  /auth/me
GET  /workspace/dashboard
GET  /workspace/projects        POST /workspace/projects
POST /workspace/projects/{id}/share
GET  /workspace/datasets        POST /workspace/datasets/upload
GET  /workspace/runs            POST /workspace/runs
POST /workspace/comparisons
POST /workspace/runs/{id}/bundle
```

### Market expansion

```
GET  /gaming/world              — Godot-optimised world state
GET  /gaming/world_seed?dataset=gdelt
POST /gaming/player_move        — WASD observer beam
GET  /gaming/players            — multiplayer registry
GET  /gaming/leaderboard
WS   /gaming/ws                 — 50ms game loop WebSocket
GET  /gaming/godot_schema       — GDScript integration guide
GET  /gaming/unity_schema       — C# integration guide

GET  /education/tour/{pack_id}
POST /education/tour/{pack_id}/session
POST /education/tour/{pack_id}/step
GET  /education/worksheet/{run_id}
GET  /education/glossary
POST /education/quiz

GET  /biomes/lore/{slug}        — LLM biome descriptions
GET  /biomes/current
GET  /biomes/world_description

GET  /billing/plans
GET  /billing/subscription
POST /billing/checkout          — Stripe checkout
POST /billing/webhook           — Stripe events
GET  /billing/usage

GET  /narratives                — available scenario packs
GET  /narratives/{id}
GET  /sdk/schema
GET  /sdk/exports/latest        — Unity/Unreal/Godot polling endpoint
POST /bundles/repro             — signed reproducibility bundle
```

---

## Configuration

Copy `.env.example` to `.env`:

```env
DATABASE_URL=postgresql://geolatent:geolatent@localhost:5432/geolatent
GEOLATENT_JWT_SECRET=<openssl rand -hex 32>
GEOLATENT_AUDIT_SIGNING_KEY=<openssl rand -hex 32>
GEOLATENT_BUNDLE_SECRET=<openssl rand -hex 32>
GEOLATENT_ALLOW_HEADER_DEV=false          # NEVER true in production
GEOLATENT_OIDC_JWKS_URI=                  # Clerk/Auth0/Cognito JWKS URL
STRIPE_SECRET_KEY=
ANTHROPIC_API_KEY=                        # enables LLM biome lore
```

---

## Gaming & entertainment integration

### Godot 4

```gdscript
# geo_latent_client.gd
var ws := WebSocketPeer.new()

func _ready():
    ws.connect_to_url("ws://localhost:8000/gaming/ws")

func _process(_delta):
    ws.poll()
    if ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
        while ws.get_available_packet_count() > 0:
            var msg = JSON.parse_string(ws.get_packet().get_string_from_utf8())
            if msg.type == "world":
                update_terrain(msg)   # msg.terrain, msg.biomes, msg.anomalies

func move(x: float, y: float):
    ws.send_text(JSON.stringify({"type":"move","x":x,"y":y,"radius":0.1}))
```

See `GET /gaming/godot_schema` for the complete integration guide.

### Unity

Poll `GET /sdk/exports/latest` every 100ms. See `GET /gaming/unity_schema` for the C# snippet.

### World seeds (live public data)

| Seed | Source | Terrain metaphor |
|---|---|---|
| `gdelt` | GDELT event database | Geopolitical tension landscape |
| `openaq` | Air quality monitors | Pollution density terrain |
| `finance` | Transaction velocity | Fraud canyon / legitimate mountain |
| `climate` | Climate indicators | Temperature anomaly drift |
| `sports` | Match events | Attack vs defence dominance |

```
GET /gaming/world_seed?dataset=gdelt
```

---

## Education integration

```
GET /education/tour/intro-to-kde          — 5-step guided KDE walkthrough
GET /education/tour/fraud-detection-tour  — financial risk analyst tour
GET /education/glossary                   — full terminology reference
GET /education/datasets                   — curated teaching datasets
GET /education/worksheet/{run_id}         — markdown student worksheet
POST /education/quiz                      — auto-generated quiz
```

---

## Billing tiers

| Tier | Price | Steps | SDK exports | Bundles | Gaming WS | SSO |
|---|---|---|---|---|---|---|
| Free | $0 | 100/mo | — | — | — | — |
| Research | $49/mo | unlimited | — | ✓ | — | — |
| Studio | $199/mo | unlimited | ✓ | ✓ | ✓ | — |
| Enterprise | contact | unlimited | ✓ | ✓ | ✓ | ✓ |

---

## Running tests

```bash
pip install -r requirements.txt
pytest                           # 39 tests across all five layers
pytest -v geolatent/tests/       # verbose
```

---

## Database migrations

```bash
alembic upgrade head             # apply all migrations
alembic revision --autogenerate -m "add column"   # create new migration
alembic downgrade base           # roll back everything
```

---

## Deployment

### Railway (fastest — zero config)

```bash
railway login
railway init
railway up
```

Set environment variables in the Railway dashboard. `railway.toml` is included.

### Kubernetes / ECS

```bash
docker build -t geo-latent:3.0 .
# Push to your registry, then deploy with the provided docker-compose.yml as reference
```

Production checklist:
- Rotate all three secret keys (`openssl rand -hex 32`)
- Set `GEOLATENT_ALLOW_HEADER_DEV=false`
- Configure managed Postgres (Neon, Supabase, RDS)
- Configure Redis (Upstash, ElastiCache)
- Set `GEOLATENT_OIDC_JWKS_URI` for SSO (Clerk, Auth0)
- Point Stripe webhook at `POST /billing/webhook`
- Run `alembic upgrade head` on first deploy

---

## Module map

```
geolatent/
  api.py             FastAPI app — all endpoints, lifespan, router inclusion
  server.py          ASGI entrypoint (uvicorn geolatent.server:app)
  cli.py             CLI: run / replay / serve
  simulator.py       KDE terrain, water cycle, predator-prey, immortal cells
  engine.py          Orchestration loop — wraps WorldState for the API
  metrics.py         Stability Index, Shannon entropy, drift, bias
  policy.py          EMA policy agent — sea rise, temperature boost, pruning
  mesh.py            OBJ + scene JSON export for 3-D clients
  adapters.py        CSV / JSONL → DataPoint (with prototype pollution guard)
  scenarios.py       Inflow generators for all built-in scenarios
  entities.py        Fossil, mist, beacon synthesis
  visualization.py   ASCII terminal renderer
  auth.py            HS256 + RS256/OIDC JWT, workspace auth flows
  persistence.py     File-backed snapshot / replay
  persistence_db.py  PostgreSQL schema, async connection pool, audit log
  gaming.py          Godot/Unity bridge, player registry, world seeds
  education.py       Guided tours, worksheets, quiz generation
  biome_lore.py      LLM biome descriptions (Claude API + procedural fallback)
  billing.py         Stripe tiers, tier gates, usage metering
  demo.py            Standalone demo — no server required
  tests/test_all.py  39 regression tests
docs/viewer/
  index.html         Three.js 3-D viewer (served at /)
alembic/             Database migrations
```

---

## Changelog

### v3.0.0 (current)

**Bug fixes:**
- `api.py` — `@app.on_event` replaced with `@asynccontextmanager` lifespan (FastAPI 0.95+)
- `persistence_db.py` — per-request `_connect()` replaced with `AsyncConnectionPool` on `app.state`
- `simulator.py` — KDE loop vectorized with numpy: O(N·σ²) vs previous O(W·H·N), ~10–100× faster
- `auth.py` — RS256/OIDC JWKS path added alongside HS256 (enables Clerk, Auth0, Cognito)
- `policy.py` — `PolicyIntervention(step=None)` bug fixed at all three call sites
- `docker-compose.yml` — `ACCEPT_DEV_HEADERS` default changed to `false`; deprecated `version:` key removed; healthchecks added
- Removed `test.py` (`print("Hi, my name is Alban")`) and empty `staging.py`

**New infrastructure:**
- `geolatent/gaming.py` — Godot/Unity/Unreal bridge, WASD player movement, multiplayer registry, world seeds
- `geolatent/education.py` — guided tours, quiz generation, worksheet export, curated teaching datasets
- `geolatent/biome_lore.py` — Claude API biome descriptions with procedural fallback
- `geolatent/billing.py` — Stripe checkout/portal/webhook, four-tier model, `check_gate()` helper
- `docs/viewer/index.html` — full Three.js 3-D viewer: terrain, event horizons, ghost geometry, observer beams, all HUD panels
- `alembic/` — proper database migrations replacing fragile `CREATE TABLE IF NOT EXISTS`
- `conftest.py` — lifespan mock so all tests run without Postgres/Redis

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built with FastAPI, Three.js, numpy, PostgreSQL, TimescaleDB, Stripe, and the Claude API.*
