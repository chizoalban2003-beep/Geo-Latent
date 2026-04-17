#!/usr/bin/env bash
# =============================================================================
# setup.sh — One-command Geo-latent GitHub setup
#
# Downloads the project from the bundle, creates the GitHub repo under your
# account, and pushes all code in a single run.
#
# USAGE:
#   curl -fsSL https://raw.githubusercontent.com/chizoalban2003-beep/geo-latent/main/setup.sh | bash
#
# OR after downloading this file:
#   GITHUB_TOKEN=ghp_xxxx bash setup.sh
#
# REQUIREMENTS:
#   - git
#   - curl
#   - A GitHub personal access token with 'repo' scope
#     Get one at: https://github.com/settings/tokens/new?scopes=repo&description=geo-latent-setup
# =============================================================================
set -euo pipefail

OWNER="chizoalban2003-beep"
REPO="geo-latent"
DESCRIPTION="Spatial Data-OS — transform any dataset into a navigable 3D ecological simulation"
BUNDLE_URL="https://github.com/${OWNER}/geo-latent/raw/main/geo-latent-v3.bundle"
WORKDIR="${HOME}/geo-latent-setup"

# ── Colour output ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; AMBER='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}==>${NC} $*"; }
warn()  { echo -e "${AMBER}  →${NC} $*"; }
error() { echo -e "${RED}ERROR:${NC} $*" >&2; exit 1; }

# ── Token ────────────────────────────────────────────────────────────────────
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo ""
  echo "  A GitHub personal access token is required."
  echo "  Create one at: https://github.com/settings/tokens/new?scopes=repo&description=geo-latent-setup"
  echo ""
  read -rsp "  Paste your token (input hidden): " GITHUB_TOKEN
  echo ""
fi
[[ -z "$GITHUB_TOKEN" ]] && error "Token cannot be empty."

# ── Check if repo already exists ─────────────────────────────────────────────
info "Checking GitHub for existing repo ${OWNER}/${REPO} ..."
HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  "https://api.github.com/repos/${OWNER}/${REPO}")

if [[ "$HTTP" == "200" ]]; then
  warn "Repo ${OWNER}/${REPO} already exists — will push to it."
  CLONE_URL="https://github.com/${OWNER}/${REPO}.git"
else
  info "Creating repo ${OWNER}/${REPO} on GitHub ..."
  RESPONSE=$(curl -s -X POST \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/user/repos" \
    -d "{
      \"name\": \"${REPO}\",
      \"description\": \"${DESCRIPTION}\",
      \"private\": false,
      \"auto_init\": false,
      \"has_issues\": true,
      \"has_wiki\": false
    }")
  CLONE_URL=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('clone_url',''))")
  [[ -z "$CLONE_URL" ]] && error "Failed to create repo. Response: $RESPONSE"
  info "Created: $CLONE_URL"
fi

# ── Set up working directory ──────────────────────────────────────────────────
rm -rf "$WORKDIR" && mkdir -p "$WORKDIR"
cd "$WORKDIR"

# ── Download the bundle ───────────────────────────────────────────────────────
BUNDLE_FILE="geo-latent-v3.bundle"

if [[ -f "${HOME}/Downloads/geo-latent-v3.bundle" ]]; then
  info "Using bundle from ~/Downloads/"
  cp "${HOME}/Downloads/geo-latent-v3.bundle" "$BUNDLE_FILE"
elif [[ -f "${HOME}/geo-latent-v3.bundle" ]]; then
  info "Using bundle from ~/"
  cp "${HOME}/geo-latent-v3.bundle" "$BUNDLE_FILE"
else
  info "Downloading bundle from GitHub ..."
  curl -fsSL -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    "${BUNDLE_URL}" -o "$BUNDLE_FILE" 2>/dev/null || true
  if [[ ! -s "$BUNDLE_FILE" ]]; then
    warn "Bundle not yet on GitHub. Using local fallback..."
    # If this script is running from the extracted tarball directory, use that
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
    if [[ -d "$SCRIPT_DIR/.git" ]]; then
      info "Found local repo at $SCRIPT_DIR — using it directly"
      cd "$SCRIPT_DIR"
      git remote set-url origin "https://${GITHUB_TOKEN}@${CLONE_URL#https://}"
      git branch -M main
      git push -u origin main
      echo ""
      info "Done! Your repo is live at: https://github.com/${OWNER}/${REPO}"
      exit 0
    fi
    error "Could not find bundle or local repo. Download geo-latent-v3.bundle to ~/Downloads/ first."
  fi
fi

# ── Clone from bundle and push ────────────────────────────────────────────────
info "Cloning from bundle ..."
git clone "$BUNDLE_FILE" repo
cd repo

git config user.email "${OWNER}@users.noreply.github.com"
git config user.name  "$OWNER"
git branch -M main
git remote set-url origin "https://${GITHUB_TOKEN}@${CLONE_URL#https://}"

info "Pushing to https://github.com/${OWNER}/${REPO} ..."
git push -u origin main

# ── Update repo metadata ─────────────────────────────────────────────────────
info "Setting repo topics and homepage ..."
curl -s -X PUT \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${OWNER}/${REPO}/topics" \
  -d '{"names":["data-visualization","3d","simulation","fastapi","python","saas","kde","terrain-generation","gaming","education"]}' \
  > /dev/null

curl -s -X PATCH \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/${OWNER}/${REPO}" \
  -d "{\"homepage\": \"https://${REPO}.up.railway.app\", \"has_issues\": true}" \
  > /dev/null

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Geo-latent v3.0.0 is live on GitHub                ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  Repo:    https://github.com/${OWNER}/${REPO}"
echo "  Clone:   git clone https://github.com/${OWNER}/${REPO}.git"
echo ""
echo "  Next steps:"
echo "  1. Deploy:  railway up   (railway.toml is included)"
echo "  2. Secrets: copy .env.example → .env, fill in real values"
echo "  3. DB:      alembic upgrade head"
echo "  4. Run:     python3 -m geolatent serve --scenario neutral_baseline --steps 20"
echo ""
