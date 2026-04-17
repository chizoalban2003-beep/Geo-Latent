# Contributing to Geo-latent

## Quick start

```bash
git clone https://github.com/chizoalban2003-beep/Geo-Latent.git
cd Geo-Latent
pip install -r requirements.txt
cp .env.example .env          # set GEOLATENT_MODE=dev, leave DATABASE_URL blank
python3 -m geolatent.demo     # smoke test — no server needed
pytest geolatent/tests/ -v    # 68 tests, all should pass
```

## Running locally

```bash
# Without Docker (stateless — no DB needed)
uvicorn geolatent.server:app --host 0.0.0.0 --port 8000

# With Docker (full stack — Postgres + Redis)
docker compose up --build
```

Open `http://localhost:8000` for the viewer and `http://localhost:8000/docs` for Swagger.

## Adding a new endpoint

1. If it belongs to an existing module (`gaming`, `education`, `billing`, `biome_lore`, `cael`, `performance`) — add the route to that module's `router`.
2. If it's a new feature area — create `geolatent/myfeature.py` with `router = APIRouter()`, then register it inside `_include_expansion_routers()` at the bottom of `api.py`.
3. Add at least one happy-path and one edge/error test in `geolatent/tests/test_all.py`.
4. If the endpoint is gated behind a billing tier, call `require_gate(auth["tenant_id"], "gate_name")` at the top of the handler.
5. If the new module introduces domain-specific vocabulary, add its tokens to `geolatent/cael.py` under each of the four themes.

## Adding a database table

Never write `CREATE TABLE` in application code. Always use Alembic:

```bash
alembic revision --autogenerate -m "describe the change"
# Review the generated file in alembic/versions/
alembic upgrade head
```

## Test conventions

- All tests live in `geolatent/tests/test_all.py`
- `conftest.py` provides `mock_pool` and `mock_engine` — no real DB required
- Group tests by module/layer using `class TestModuleName:`
- Every new module needs at minimum: one happy-path test, one edge case, one mutation/isolation test
- Run `pytest -v` before opening a PR — all 68 tests must pass

## Code conventions

- Python 3.12, no `type: ignore` unless strictly unavoidable
- `from __future__ import annotations` at the top of every module
- Functions that touch incoming dicts must call `_sanitise()` from `adapters.py`
- Database functions take `conn` as first argument — never open connections inside them
- All new FastAPI routes use `Depends(get_auth)` for auth context
- EMA smoothing (α = 0.3) on any metric that feeds the policy agent
- Lazy imports inside functions when a circular import risk exists (e.g. collision.py ↔ simulator.py)

## Commit message format

```
type: short description (≤72 chars)

Longer explanation if needed. Reference issue numbers with #N.
```

Types: `feat` / `fix` / `chore` / `docs` / `test` / `refactor`

## Branch strategy

- `main` — always deployable, CI must be green
- `feat/my-feature` — feature branches, PR to main
- Squash-merge preferred for feature branches to keep history clean
