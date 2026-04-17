# Contributing to Geo-latent

## Quick start

```bash
git clone https://github.com/chizoalban2003-beep/geo-latent.git
cd geo-latent
pip install -r requirements.txt
cp .env.example .env          # fill in secrets (dev values are fine locally)
python3 -m geolatent.demo     # smoke test — no server needed
pytest geolatent/tests/ -v    # run the full test suite
```

## Running locally with the full stack

```bash
docker compose up --build     # starts app + Postgres + Redis
open http://localhost:8000    # Three.js viewer
open http://localhost:8000/docs  # Swagger API docs
```

## Adding a new endpoint

1. If it belongs to an existing module (`gaming`, `education`, `billing`, `biome_lore`) — add the route to that module's `router`.
2. If it's a new feature area — create `geolatent/myfeature.py` with a `router = APIRouter()`, then add `app.include_router(...)` at the bottom of `api.py` inside `_include_expansion_routers()`.
3. Add at least two tests in `geolatent/tests/test_all.py`.
4. If the endpoint is gated behind a billing tier, call `require_gate(auth["tenant_id"], "gate_name")` at the top of the handler.

## Adding a database table

Never write `CREATE TABLE` in application code. Always use Alembic:

```bash
alembic revision --autogenerate -m "describe the change"
# Review the generated file in alembic/versions/
alembic upgrade head
```

## Test conventions

- Tests live in `geolatent/tests/test_all.py`
- `conftest.py` provides `mock_pool` and `mock_engine` — no real DB required
- Group tests by layer using `class TestLayerName:`
- Every new module gets at minimum: one happy-path test and one edge/error test

## Code conventions

- Python 3.12, no type-ignore unless unavoidable
- `from __future__ import annotations` at the top of every module
- Functions that touch incoming dicts must call `_sanitise()` from `adapters.py`
- Database functions take `conn` as first argument — never open connections inside them
- All new FastAPI routes use `Depends(get_auth)` for auth context
- EMA smoothing on any metric that feeds the policy agent

## Commit message format

```
type: short description (≤72 chars)

Longer explanation if needed. Reference issue numbers with #N.
```

Types: `feat` / `fix` / `chore` / `docs` / `test` / `refactor`

## Branch strategy

- `main` — always deployable
- `feat/my-feature` — feature branches, PR to main
- CI must be green before merge
