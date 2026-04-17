# Geo-latent v3.1 — Spatial Data-OS

> Transform any dataset into a navigable, self-regulating 3-D ecological simulation.

[![Tests](https://img.shields.io/badge/tests-68%20passing-brightgreen)](geolatent/tests/test_all.py)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## What it is

Geo-latent is a universal SaaS platform that ingests any structured dataset — financial transactions, genomic sequences, network logs, climate sensors, game events — and synthesises it into a continuous, interactive 3-D terrain using **Kernel Density Estimation** and **ecological simulation physics**.

High-density data clusters become mountain ranges. Anomalies invert into glowing **gravity-well canyons**. Two competing datasets fight for terrain dominance via **Lotka-Volterra predator-prey dynamics**. The system monitors its own Shannon entropy and applies homeostatic corrections through an **EMA policy agent**. Every cell that remains stable for 1,000 consecutive ticks is etched into a **FIFO Immortal Cell ledger**. A **ghost lookahead** projects 3 steps into the future as a translucent wireframe overlay. And the entire simulation speaks your domain's language via the **CAEL vocabulary layer** — genomics, finance, void, or smart city.

The same engine powers:
- **Research SaaS** — fraud/AML terrain, genomics drift, cyber anomaly detection
- **Education** — guided KDE tours, student worksheets, quiz generation
- **Gaming** — Godot/Unity/Unreal integration, observer-as-player, multiplayer worlds
- **Entertainment** — live data planetarium, museum installations, procedural world generation

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 1 — Ingestion & Security Boundary                          │
│  REST/WS gateway · JWT/OIDC auth · prototype pollution guards     │
│  multi-observer sync registry · ephemeral 30s WS tokens           │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2 — Core Physics & Mathematical Engine                     │
│  KDE geomorphology · gravity-well inversion · Lotka-Volterra      │
│  predator-prey terrain erosion · numpy-vectorized O(N·σ²)         │
│  observer Gaussian depression · ghost lookahead shadow simulation  │
├──────────────────────────────────────────────────────────────────┤
│  Layer 3 — Autonomic Homeostasis                                  │
│  Shannon entropy · entropy lightning · EMA policy agent (α=0.3)   │
│  sea-level homeostasis · Gaussian pruning · carrying capacity      │
├──────────────────────────────────────────────────────────────────┤
│  Layer 4 — Rendering & Sensory Frontend                           │
│  Three.js 3-D terrain · CAEL semantic log · biome lore (LLM)      │
│  Web Audio entropy oscillator · plasma cones · ghost wireframe     │
│  observer beams · event horizon rings · entropy lightning          │
├──────────────────────────────────────────────────────────────────┤
│  Layer 5 — Post-Game Analytics & Temporal Ledger                  │
│  Immortal cell FIFO tracking · Stability Index S = ∫ROI/H dt      │
│  ROI performance grades (A–D) · signed reproducibility bundles     │
│  TimescaleDB hypertable · CAEL vocabulary translation              │
└──────────────────────────────────────────────────────────────────┘
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

### Option A — Docker (recommended, full stack)

```bash
cp .env.example .env          # fill in real secrets
docker compose up --build     # starts app + Postgres + Redis
```

Open: `http://localhost:8000/`

### Option B — Local Python (no Docker)

```bash
pip install -r requirements.txt
cp .env.example .env          # set GEOLATENT_MODE=dev, leave DATABASE_URL blank to skip DB
uvicorn geolatent.server:app --host 0.0.0.0 --port 8000
```

Open: `http://localhost:8000/`  
Interactive docs: `http://localhost:8000/docs`

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

**Direct injection** (no file upload):

```bash
curl -X POST http://localhost:8000/nexus/inflow \
  -H "Content-Type: application/json" \
  -d '{"points": [{"x": 0.5, "y": 0.5, "energy": 2.0, "kind": "neutral"}]}'
```

---

## API reference

Full interactive docs at `http://localhost:8000/docs`.

### Core simulation

```
GET  /health                    — engine + db + redis status
GET  /health/detailed           — full system introspection
GET  /frame                     — current simulation frame (step, anomalies, sea_level …)
GET  /frame/lookahead?steps=3   — ghost projection: 3-step shadow simulation scene
GET  /scene                     — 3-D mesh (vertices, faces, biomes)
GET  /report                    — stability index, drift, entropy, immortal cells
GET  /performance               — ROI score 0–1, grade A–D, sub-scores
GET  /controls                  — current runtime controls
POST /controls                  — update controls (variance, temperature, observer …)
POST /step                      — advance one tick
POST /pause | /resume
POST /nexus/inflow              — inject points / CSV / text into running engine
GET  /nexus/schema              — integration contract
WS   /ws                        — real-time stream (30s JWT challenge)
```

### CAEL — Contextual AI Event Layer

```
GET  /cael/themes               — list available vocabulary themes
GET  /cael/translate?token=&theme=  — translate a single token
POST /cael/frame                — translate a full frame dict to domain language
```

Themes: `genomics` · `finance` · `void` · `smart_city`

### Auth

```
POST /auth/bootstrap            — one-time admin setup (requires DATABASE_URL)
POST /auth/login                — issue JWT
POST /auth/dev-token            — issue dev JWT without database (dev/demo mode)
GET  /auth/me
```

### Workspace SaaS

```
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
POST /billing/portal            — Stripe customer portal
POST /billing/webhook           — Stripe events
GET  /billing/usage
GET  /billing/tier_check/{gate}

GET  /narratives                — available scenario packs
GET  /sdk/schema
GET  /sdk/exports/latest        — Unity/Unreal/Godot polling endpoint
POST /bundles/repro             — signed reproducibility bundle
```

---

## Configuration

Copy `.env.example` to `.env`:

```env
# Required for full persistence — leave blank to run stateless (dev/demo)
DATABASE_URL=postgresql://geolatent:geolatent@localhost:5432/geolatent

# MUST be rotated before production (generate with: openssl rand -hex 32)
GEOLATENT_JWT_SECRET=changeme
GEOLATENT_AUDIT_SIGNING_KEY=changeme
GEOLATENT_BUNDLE_SECRET=changeme

# Dev auth — NEVER true in production
GEOLATENT_ALLOW_HEADER_DEV=false

# Runtime mode: demo | dev | production
# demo/dev  — studio tier unlocked, DB optional, verbose logging
# production — enforces tier gates, requires DATABASE_URL
GEOLATENT_MODE=production

# OIDC provider (Clerk, Auth0, Cognito)
GEOLATENT_OIDC_JWKS_URI=

# Stripe billing
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_RESEARCH=
STRIPE_PRICE_STUDIO=
STRIPE_PRICE_ENTERPRISE=

# Optional: enables LLM biome lore (falls back to procedural lore if unset)
ANTHROPIC_API_KEY=
```

---

## CAEL — Vocabulary Translation

The Contextual AI Event Layer translates canonical simulation tokens into domain-specific language, making the same engine feel native to different industries.

| Canonical | `genomics` | `finance` | `void` | `smart_city` |
|---|---|---|---|---|
| `active` | expressed_genes | open_positions | astral_entities | active_sensors |
| `abyss` | silenced_sequences | delisted_assets | collapsed_singularities | offline_nodes |
| `sea_level` | expression_threshold | liquidity_floor | void_horizon | congestion_threshold |
| `gravity_well` | silencer_element | circuit_breaker | black_hole | congestion_hotspot |
| `immortal` | housekeeping_gene | blue_chip_anchor | eternal_attractor | critical_infrastructure |

```bash
# Translate a frame to genomics vocabulary
curl -X POST http://localhost:8000/cael/frame \
  -H "Content-Type: application/json" \
  -d '{"frame": {"active": 42, "abyss": 5, "sea_level": 0.2}, "theme": "genomics"}'
```

---

## Gaming & entertainment integration

### Godot 4

```gdscript
# geo_latent_client.gd
var ws := WebSocketPeer.new()

func _ready():
    ws.connect_to_url("ws://YOUR_SERVER:PORT/gaming/ws")

func _process(_delta):
    ws.poll()
    if ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
        while ws.get_available_packet_count() > 0:
            var msg = JSON.parse_string(ws.get_packet().get_string_from_utf8())
            if msg.type == "world":
                update_terrain(msg)

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
pytest                           # 68 tests across all five layers + new modules
pytest -v geolatent/tests/       # verbose
```

---

## Database migrations

```bash
alembic upgrade head             # apply all migrations
alembic revision --autogenerate -m "describe the change"
alembic downgrade base           # roll back everything
```

---

## Deployment

### Railway (fastest — one command)

```bash
railway login && railway init && railway up
```

Set environment variables in the Railway dashboard. `railway.toml` is included. The start command conditionally runs `alembic upgrade head` only when `DATABASE_URL` is set.

### Docker Compose (local full stack)

```bash
cp .env.example .env   # fill in secrets
docker compose up --build
```

### Kubernetes / ECS

```bash
docker build -t geo-latent:3.1 .
# Push to your registry, use docker-compose.yml as reference
```

### Production checklist

- [ ] Rotate all three secrets (`openssl rand -hex 32` for each)
- [ ] Set `GEOLATENT_ALLOW_HEADER_DEV=false`
- [ ] Set `GEOLATENT_MODE=production`
- [ ] Configure managed Postgres (Neon, Supabase, RDS)
- [ ] Configure Redis (Upstash, ElastiCache)
- [ ] Set `GEOLATENT_OIDC_JWKS_URI` for SSO (Clerk, Auth0)
- [ ] Point Stripe webhook at `POST /billing/webhook`
- [ ] Run `alembic upgrade head` on first deploy
- [ ] Set `GEOLATENT_PUBLIC_URL` to your deployment domain

---

## Module map

```
geolatent/
  api.py             FastAPI app — all endpoints, lifespan, router inclusion
  server.py          ASGI entrypoint — loads .env, warms engine (uvicorn geolatent.server:app)
  cli.py             CLI: run / replay / serve
  simulator.py       KDE terrain, water cycle, gravity wells, observer depression
  engine.py          Orchestration loop — WorldState wrapper + lookahead()
  collision.py       Lotka-Volterra predator-prey module + run_collision() API
  genealogy.py       Immortal cell FIFO ledger (2000-entry cap, ≥1000 tick threshold)
  metrics.py         Stability Index, Shannon entropy, drift, bias, immortal cells
  performance.py     ROI analytics — score 0–1, grade A–D + GET /performance
  policy.py          EMA policy agent (α=0.3) — sea rise, temperature boost, pruning
  cael.py            CAEL vocabulary router — 4 themes × 16 tokens + GET /cael endpoints
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
  tests/test_all.py  68 tests across all five layers + new modules
docs/viewer/
  index.html         Three.js 3-D viewer — terrain, plasma cones, ghost wireframe,
                     Web Audio entropy oscillator, observer beams, CAEL HUD
alembic/             Database migrations
```

---

## Changelog

### v3.1.0 (current)

**New modules:**
- `geolatent/collision.py` — Lotka-Volterra extracted to clean module; `run_collision(world_a, world_b, steps)` two-world simulation API
- `geolatent/performance.py` — ROI-based performance analytics: score 0–1, grade A–D, `GET /performance`
- `geolatent/cael.py` — CAEL vocabulary router: 4 themes × 16 tokens, `GET /cael/themes|translate`, `POST /cael/frame`
- `geolatent/genealogy.py` — Immortal cell FIFO ledger: 2000-entry cap, ≥1000 tick threshold, OrderedDict migration

**Engine:**
- `engine.py` — `lookahead(steps=3)`: deep-copies state, runs shadow simulation, returns projected scene
- `api.py` — `GET /frame/lookahead?steps=N`: ghost shadow endpoint with `asyncio.to_thread`
- `metrics.py` — immortal threshold now delegates to `genealogy.get_immortal_cells()` (canonical ≥1000)
- `policy.py` — EMA alpha corrected to 0.3 (spec requirement)
- `simulator.py` — delegates `apply_lotka_volterra` and immortal tracking to new modules

**Infrastructure:**
- `server.py` + `api.py` — automatic `.env` loading at import time (python-dotenv + manual fallback)
- `Dockerfile` + `railway.toml` — conditional `alembic upgrade head` (only runs when `DATABASE_URL` is set); `$PORT` env var support
- `__init__.py` — version bumped to 3.1.0

**Viewer (`docs/viewer/index.html`):**
- Web Audio API: OscillatorNode 55→165 Hz modulated by Shannon entropy, white noise layer, `♪ Audio ON/OFF` toggle
- Plasma cones: purple `THREE.ConeGeometry` at each anomaly cell, pulsing opacity animation
- Ghost lookahead wireframe: translucent blue terrain overlay from `/frame/lookahead`, refreshed every 5 s

**Tests:**
- 68 tests total (was 47): added `TestCael` (6), `TestCollision` (5), `TestGenealogy` (5), `TestPerformance` (5)

---

### v3.0.0

**Bug fixes:**
- `api.py` — `@app.on_event` replaced with `@asynccontextmanager` lifespan (FastAPI 0.95+)
- `persistence_db.py` — per-request `_connect()` replaced with `AsyncConnectionPool` on `app.state`
- `simulator.py` — KDE loop vectorized with numpy: O(N·σ²) vs previous O(W·H·N), ~10–100× faster
- `auth.py` — RS256/OIDC JWKS path added alongside HS256 (enables Clerk, Auth0, Cognito)
- `policy.py` — `PolicyIntervention(step=None)` bug fixed at all three call sites
- `docker-compose.yml` — `ACCEPT_DEV_HEADERS` default changed to `false`; deprecated `version:` key removed; healthchecks added
- Removed `test.py` and empty `staging.py`

**New infrastructure:**
- `geolatent/gaming.py` — Godot/Unity/Unreal bridge, WASD player movement, multiplayer registry, world seeds
- `geolatent/education.py` — guided tours, quiz generation, worksheet export, curated teaching datasets
- `geolatent/biome_lore.py` — Claude API biome descriptions with procedural fallback
- `geolatent/billing.py` — Stripe checkout/portal/webhook, four-tier model, `check_gate()` helper
- `docs/viewer/index.html` — full Three.js 3-D viewer: terrain, event horizons, observer beams, CAEL HUD
- `alembic/` — proper database migrations replacing fragile `CREATE TABLE IF NOT EXISTS`
- `conftest.py` — lifespan mock so all tests run without Postgres/Redis
- `simulator.py` — gravity-well inversion, observer Gaussian depression

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built with FastAPI · Three.js · numpy · PostgreSQL · TimescaleDB · Stripe · Claude API*
