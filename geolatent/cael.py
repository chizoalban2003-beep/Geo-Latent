"""
geolatent/cael.py
Contextual AI Event Layer — vocabulary swaps per simulation theme.

Themes: genomics | finance | void | smart_city
Each theme maps canonical event tokens to domain-specific language.

Exposes:
  translate(token, theme) -> str
  translate_frame(frame, theme) -> dict   (renames keys + values)
  GET /cael/themes        — list available themes
  GET /cael/translate     — translate a token
  POST /cael/frame        — translate a full frame dict
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()

# ---------------------------------------------------------------------------
# Vocabulary tables
# ---------------------------------------------------------------------------

_VOCAB: dict[str, dict[str, str]] = {
    "genomics": {
        "active":       "expressed_genes",
        "abyss":        "silenced_sequences",
        "atmosphere":   "latent_epigenome",
        "sea_level":    "expression_threshold",
        "terrain_mu":   "mean_expression",
        "terrain_sigma":"expression_variance",
        "energy":       "transcription_rate",
        "prey":         "regulatory_activator",
        "predator":     "repressor_complex",
        "immortal":     "housekeeping_gene",
        "biome":        "chromatin_domain",
        "drift":        "somatic_drift",
        "entropy":      "regulatory_entropy",
        "stability":    "homeostatic_index",
        "observer":     "sequencer_focus",
        "gravity_well": "silencer_element",
    },
    "finance": {
        "active":       "open_positions",
        "abyss":        "delisted_assets",
        "atmosphere":   "dark_pool_orders",
        "sea_level":    "liquidity_floor",
        "terrain_mu":   "mean_price_surface",
        "terrain_sigma":"price_volatility",
        "energy":       "market_cap",
        "prey":         "long_position",
        "predator":     "short_position",
        "immortal":     "blue_chip_anchor",
        "biome":        "market_sector",
        "drift":        "price_drift",
        "entropy":      "market_entropy",
        "stability":    "sharpe_proxy",
        "observer":     "market_maker",
        "gravity_well": "circuit_breaker",
    },
    "void": {
        "active":       "astral_entities",
        "abyss":        "collapsed_singularities",
        "atmosphere":   "quantum_foam",
        "sea_level":    "void_horizon",
        "terrain_mu":   "mean_density",
        "terrain_sigma":"curvature_variance",
        "energy":       "dark_energy",
        "prey":         "luminous_matter",
        "predator":     "dark_matter",
        "immortal":     "eternal_attractor",
        "biome":        "spacetime_region",
        "drift":        "cosmic_drift",
        "entropy":      "thermodynamic_entropy",
        "stability":    "manifold_integrity",
        "observer":     "observation_collapse",
        "gravity_well": "black_hole",
    },
    "smart_city": {
        "active":       "active_sensors",
        "abyss":        "offline_nodes",
        "atmosphere":   "edge_cache",
        "sea_level":    "congestion_threshold",
        "terrain_mu":   "mean_traffic_density",
        "terrain_sigma":"traffic_variance",
        "energy":       "bandwidth",
        "prey":         "pedestrian_flow",
        "predator":     "vehicle_flow",
        "immortal":     "critical_infrastructure",
        "biome":        "urban_zone",
        "drift":        "demand_drift",
        "entropy":      "network_entropy",
        "stability":    "service_uptime",
        "observer":     "camera_cluster",
        "gravity_well": "congestion_hotspot",
    },
}

THEMES = list(_VOCAB.keys())


def translate(token: str, theme: str) -> str:
    """Return domain-specific label for a canonical token under the given theme."""
    return _VOCAB.get(theme, {}).get(token, token)


def translate_frame(frame: dict, theme: str) -> dict:
    """
    Shallow-translate the keys and string values of a frame dict.
    Non-string values are passed through unchanged.
    """
    vocab = _VOCAB.get(theme, {})
    out: dict = {}
    for k, v in frame.items():
        new_k = vocab.get(k, k)
        new_v = vocab.get(v, v) if isinstance(v, str) else v
        out[new_k] = new_v
    return out


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@router.get("/themes")
async def list_themes():
    return {"themes": THEMES, "token_count": {t: len(v) for t, v in _VOCAB.items()}}


@router.get("/translate")
async def translate_token(
    token: str = Query(..., description="Canonical token to translate"),
    theme: str = Query("void", description="Target theme"),
):
    if theme not in _VOCAB:
        return {"error": f"Unknown theme '{theme}'. Available: {THEMES}"}
    return {
        "token":       token,
        "theme":       theme,
        "translation": translate(token, theme),
    }


class FrameTranslateRequest(BaseModel):
    frame: dict
    theme: str = "void"


@router.post("/frame")
async def translate_frame_endpoint(body: FrameTranslateRequest):
    if body.theme not in _VOCAB:
        return {"error": f"Unknown theme '{body.theme}'. Available: {THEMES}"}
    return {
        "theme":            body.theme,
        "translated_frame": translate_frame(body.frame, body.theme),
    }
