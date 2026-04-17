"""
geolatent/biome_lore.py
LLM-generated biome lore and narrative enrichment.

Exposes:
  GET  /biomes/lore/{biome_slug}      — get or generate lore for a biome label
  GET  /biomes/current                — all current biomes with lore
  POST /biomes/regenerate             — force-regenerate all biome lore
  GET  /biomes/world_description      — full narrative world description for loading screen

Uses the Anthropic API if ANTHROPIC_API_KEY is set.
Falls back to deterministic procedural lore when the key is absent.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Optional

from fastapi import APIRouter, Request, HTTPException

router = APIRouter()

_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_lore_cache: dict[str, dict] = {}     # biome_slug → {lore, generated_at}
_LORE_TTL = 3600                       # cache lore for 1 hour


# ---------------------------------------------------------------------------
# Procedural fallback lore (no LLM needed)
# ---------------------------------------------------------------------------

_PROCEDURAL_LORE: dict[str, str] = {
    "the-whispering-shelf":    "A vast, serene plateau where ancient data currents have long since settled. Analysts who stand here feel the quiet confidence of a signal that has found its equilibrium. Little changes; much endures.",
    "the-fracture-bloom":      "Here the earth tears itself apart in slow motion. Two data streams compete, their gradients meeting at angles that shatter the surface into crystalline ridges. Each fracture line is a decision boundary in disguise.",
    "the-tidal-archive":       "A basin that breathes with the seasons of data flow. At low tide, deep historical strata surface for inspection. At high tide, fresh inference submerges the past beneath a shimmering lens.",
    "the-crown-of-noise":      "The highest, most chaotic peaks — where entropy lightning strikes most often and the policy agent works hardest to impose order. Survive the Crown and you understand your data's wildest edges.",
    "the-null-fens":           "A sparse, marshy lowland of anomalies and outliers. Data points here drift alone, untethered from any cluster. To the trained eye, these wetlands hide the rarest fossils.",
    "the-shattering-meridian": "A belt of extreme instability that marks a regime change in the underlying distribution. Cross it and the physics of the data change fundamentally. Geologists of the manifold call it a phase transition.",
    "the-deep-trench":         "Below the sea level threshold, where stale records have sunk into the abyss. Bioluminescent mutation events flicker in the dark. Some records resurface transformed; most are never seen again.",
    "the-amber-steppe":        "A mid-variance transition belt — neither order nor chaos, but the liminal space where patterns are forming. Immortal cells first emerge here, where the land has found its rhythm.",
    "unknown-biome":           "The uncharted expanse — a region not yet fully mapped by the KDE engine. As more data arrives, its character will crystallise.",
}


def _slug(biome_label: str) -> str:
    """Convert a biome label like 'The Fracture Bloom — ...' to a URL-safe slug."""
    name = biome_label.split("—")[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def _deterministic_lore(biome_label: str) -> str:
    slug = _slug(biome_label)
    for key, lore in _PROCEDURAL_LORE.items():
        if key in slug or slug in key:
            return lore
    # Hash-deterministic fallback for unlabelled biomes
    h = int(hashlib.md5(biome_label.encode()).hexdigest(), 16) % 8
    return list(_PROCEDURAL_LORE.values())[h]


# ---------------------------------------------------------------------------
# LLM lore generation
# ---------------------------------------------------------------------------

async def _generate_lore_llm(biome_label: str) -> str:
    """
    Call Claude API to generate 2–3 sentences of world-building lore.
    Falls back gracefully if the API is unavailable.
    """
    if not _ANTHROPIC_KEY:
        return _deterministic_lore(biome_label)
    try:
        import urllib.request
        prompt = (
            f"You are the lore-writer for a data visualisation game called Geo-latent. "
            f"A biome called '{biome_label}' has formed from the user's dataset. "
            f"Write exactly 2–3 sentences of atmospheric world-building lore for this biome. "
            f"The tone is scientific-poetic — like a nature documentary crossed with a fantasy atlas. "
            f"Do not use bullet points. Output only the lore text, nothing else."
        )
        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type":      "application/json",
                "x-api-key":         _ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return data["content"][0]["text"].strip()
    except Exception:
        return _deterministic_lore(biome_label)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/lore/{biome_slug}")
async def get_biome_lore(biome_slug: str):
    """Return lore for a given biome slug, generating it if not cached."""
    cached = _lore_cache.get(biome_slug)
    if cached and time.time() - cached["generated_at"] < _LORE_TTL:
        return cached

    # Reconstruct a plausible label from slug for the LLM prompt
    label = biome_slug.replace("-", " ").title()
    lore = await _generate_lore_llm(label)
    record = {"biome_slug": biome_slug, "label": label, "lore": lore,
              "generated_at": time.time(), "source": "llm" if _ANTHROPIC_KEY else "procedural"}
    _lore_cache[biome_slug] = record
    return record


@router.get("/current")
async def current_biomes(request: Request):
    """All biomes in the current simulation, with lore."""
    engine = request.app.state.engine
    if not engine:
        return {"biomes": [], "note": "No simulation running"}

    scene = engine.current_scene()
    biomes = scene.get("biomes", {})

    unique_labels: set[str] = set(biomes.values()) if isinstance(biomes, dict) else set()
    result = []
    for label in sorted(unique_labels)[:20]:   # cap at 20 for performance
        slug = _slug(label)
        cached = _lore_cache.get(slug)
        if not cached or time.time() - cached["generated_at"] > _LORE_TTL:
            lore = _deterministic_lore(label)   # sync fallback for list view
            _lore_cache[slug] = {"biome_slug": slug, "label": label, "lore": lore,
                                  "generated_at": time.time(), "source": "procedural"}
        result.append(_lore_cache[slug])
    return {"biomes": result, "total_unique_biomes": len(unique_labels)}


@router.post("/regenerate")
async def regenerate_lore(request: Request):
    """Clear the lore cache and regenerate all biome descriptions."""
    _lore_cache.clear()
    engine = request.app.state.engine
    if not engine:
        return {"status": "cache_cleared", "biomes_regenerated": 0}

    scene = engine.current_scene()
    biomes = scene.get("biomes", {})
    unique = list(set(biomes.values()) if isinstance(biomes, dict) else [])[:10]

    regenerated = []
    for label in unique:
        slug = _slug(label)
        lore = await _generate_lore_llm(label)
        _lore_cache[slug] = {"biome_slug": slug, "label": label, "lore": lore,
                              "generated_at": time.time(),
                              "source": "llm" if _ANTHROPIC_KEY else "procedural"}
        regenerated.append(slug)

    return {"status": "ok", "biomes_regenerated": len(regenerated), "slugs": regenerated}


@router.get("/world_description")
async def world_description(request: Request):
    """
    Full narrative world description suitable for a game loading screen.
    Returns a 4–6 sentence summary of the current terrain state.
    """
    engine = request.app.state.engine
    frame  = engine.current_frame()  if engine else {}
    report = engine.current_report() if engine else {}
    scene  = engine.current_scene()  if engine else {}

    S    = report.get("stability_index", 0.75)
    sea  = frame.get("sea_level", 0.15)
    step = frame.get("step", 0)
    biomes = scene.get("biomes", {})
    dominant = max(set(biomes.values()), key=list(biomes.values()).count) if biomes else "The Uncharted Expanse"

    if _ANTHROPIC_KEY:
        prompt = (
            f"Write a 4-sentence loading-screen description for a data world in the Geo-latent engine. "
            f"Current state: step {step}, stability index {S:.2f}, sea level {sea:.2f}, "
            f"dominant biome: '{dominant}'. "
            f"Tone: cinematic, scientific-poetic. Reference the actual numbers naturally. "
            f"Output only the description text."
        )
        try:
            import urllib.request
            payload = json.dumps({
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={"Content-Type": "application/json", "x-api-key": _ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            description = data["content"][0]["text"].strip()
        except Exception:
            description = _fallback_world_description(S, sea, step, dominant)
    else:
        description = _fallback_world_description(S, sea, step, dominant)

    return {"description": description, "step": step, "stability": S,
            "dominant_biome": dominant, "generated_at": time.time()}


def _fallback_world_description(S: float, sea: float, step: int, dominant: str) -> str:
    state = "stabilised" if S > 0.7 else "in systemic collapse"
    sea_desc = "shallow" if sea < 0.3 else "rising" if sea < 0.6 else "dangerously high"
    return (
        f"At step {step}, this data world is {state} — its Stability Index reads {S:.2f}. "
        f"The dominant terrain feature is {dominant}, shaped by the underlying density distribution. "
        f"Sea levels are {sea_desc} at {sea:.2f}, {'preserving most active data clusters' if sea < 0.4 else 'drowning low-relevance signals beneath the manifold'}. "
        f"{'The policy agent has successfully maintained homeostasis.' if S > 0.7 else 'Entropy lightning is frequent; the terrain requires intervention to prevent total collapse.'}"
    )
