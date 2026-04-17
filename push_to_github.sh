#!/usr/bin/env bash
# =============================================================================
# push_to_github.sh
# Applies all geo-latent architecture fixes and market expansion files,
# renames the repo from "Git" to "geo-latent", and pushes to main.
#
# Usage:
#   GITHUB_TOKEN=ghp_xxxx bash push_to_github.sh
#
# The token needs: repo (read/write) + administration (for rename)
# =============================================================================
set -euo pipefail

OWNER="chizoalban2003-beep"
OLD_REPO="Git"
NEW_REPO="geo-latent"
BRANCH="main"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: Set GITHUB_TOKEN before running this script."
  echo "  export GITHUB_TOKEN=ghp_yourtoken"
  exit 1
fi

echo "==> Cloning ${OWNER}/${OLD_REPO} ..."
rm -rf /tmp/geo-latent-push
git clone "https://${GITHUB_TOKEN}@github.com/${OWNER}/${OLD_REPO}.git" /tmp/geo-latent-push
cd /tmp/geo-latent-push

git config user.email "geo-latent-bot@users.noreply.github.com"
git config user.name  "Geo-latent Architecture Bot"

echo "==> Copying fixed + new files ..."

# ── Critical bug fixes ────────────────────────────────────────────────────
cp "${SCRIPT_DIR}/geolatent/api.py"             geolatent/api.py
cp "${SCRIPT_DIR}/geolatent/persistence_db.py"  geolatent/persistence_db.py
cp "${SCRIPT_DIR}/geolatent/simulator.py"       geolatent/simulator.py
cp "${SCRIPT_DIR}/geolatent/auth.py"            geolatent/auth.py

# ── Market expansion (new files) ─────────────────────────────────────────
cp "${SCRIPT_DIR}/geolatent/gaming.py"          geolatent/gaming.py
cp "${SCRIPT_DIR}/geolatent/education.py"       geolatent/education.py
cp "${SCRIPT_DIR}/geolatent/biome_lore.py"      geolatent/biome_lore.py
cp "${SCRIPT_DIR}/geolatent/billing.py"         geolatent/billing.py

# ── Alembic migrations ────────────────────────────────────────────────────
mkdir -p alembic/versions
cp "${SCRIPT_DIR}/alembic/env.py"                        alembic/env.py
cp "${SCRIPT_DIR}/alembic/versions/001_baseline.py"      alembic/versions/001_baseline.py
cp "${SCRIPT_DIR}/alembic.ini"                           alembic.ini

# ── Infrastructure ────────────────────────────────────────────────────────
cp "${SCRIPT_DIR}/requirements.txt"    requirements.txt
cp "${SCRIPT_DIR}/docker-compose.yml"  docker-compose.yml
cp "${SCRIPT_DIR}/.env.example"        .env.example
cp "${SCRIPT_DIR}/conftest.py"         conftest.py

echo "==> Staging and committing ..."
git add -A
git commit -m "fix+feat: lifespan, conn-pool, numpy-KDE, OIDC; add gaming/education/billing/biome-lore; Alembic migrations; docker-compose hardening

Fixes:
- api.py: @app.on_event → @asynccontextmanager lifespan (FastAPI 0.95+ compat)
- persistence_db.py: per-request _connect() → AsyncConnectionPool on app.state
- simulator.py: pure-Python KDE loop → numpy vectorized O(N·σ²)
- auth.py: HS256-only → RS256/OIDC JWKS support (Clerk/Auth0/Cognito)
- docker-compose.yml: ACCEPT_DEV_HEADERS default false; removed version key; added healthchecks
- alembic/: Alembic migrations replace fragile CREATE TABLE IF NOT EXISTS

New market expansion infrastructure:
- geolatent/gaming.py: Godot/Unity bridge, observer-as-player, multiplayer registry, world seeds
- geolatent/education.py: guided tours, quiz generation, worksheet export, teaching datasets
- geolatent/biome_lore.py: LLM biome descriptions (Claude API, procedural fallback)
- geolatent/billing.py: Stripe tiers (free/research/studio/enterprise), tier gates, usage metering

Infrastructure:
- requirements.txt: psycopg[async], psycopg-pool, alembic, numpy, stripe, anthropic
- conftest.py: lifespan mock so all existing tests run without Postgres/Redis
- .env.example: all new env vars documented"

echo "==> Pushing to ${BRANCH} ..."
git push origin "${BRANCH}"

echo "==> Renaming repo from '${OLD_REPO}' to '${NEW_REPO}' ..."
curl -s -X PATCH \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${OWNER}/${OLD_REPO}" \
  -d "{\"name\": \"${NEW_REPO}\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Repo renamed to:', d.get('full_name', 'ERROR'), '| Clone URL:', d.get('clone_url', ''))"

echo ""
echo "==> Done! Your repo is now: https://github.com/${OWNER}/${NEW_REPO}"
echo ""
echo "Next steps:"
echo "  1. Update your Railway / Render deployment URL if it was based on the old repo name."
echo "  2. Run: alembic upgrade head   (or let docker-compose do it on next boot)"
echo "  3. Set real secrets in .env — see .env.example"
echo "  4. Enable Stripe: add STRIPE_SECRET_KEY and STRIPE_PRICE_* to .env"
echo "  5. Enable LLM lore: add ANTHROPIC_API_KEY to .env"
