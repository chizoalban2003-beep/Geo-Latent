"""
geolatent/education.py
Education tier infrastructure.

Exposes:
  GET  /education/tour/{pack_id}       — step-by-step guided walkthrough
  POST /education/tour/{pack_id}/step  — advance one guided step
  GET  /education/worksheet/{run_id}   — export markdown analysis worksheet
  GET  /education/glossary             — terminology reference
  POST /education/quiz                 — auto-generated quiz from current state
  GET  /education/datasets             — curated public teaching datasets
"""
from __future__ import annotations

import json
import math
import os
import time
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Depends

router = APIRouter()


# ---------------------------------------------------------------------------
# Guided tour sessions  (in-memory; keyed by session_id)
# ---------------------------------------------------------------------------

_tours: dict[str, dict] = {}


_TOUR_PACKS = {
    "intro-to-kde": {
        "title": "Introduction to KDE Terrain Synthesis",
        "audience": "Undergraduate data science",
        "steps": [
            {
                "index": 0,
                "title": "What is kernel density estimation?",
                "explanation": (
                    "KDE estimates the probability density of your data by placing a Gaussian "
                    "kernel over each data point and summing them. On the geo-latent terrain, "
                    "high-density regions become mountains — you are literally walking on your data."
                ),
                "controls": {"inflow_mode": "neutral", "steps": 1},
                "question": "Where are the tallest peaks? What does that tell you about your data distribution?",
            },
            {
                "index": 1,
                "title": "Variance and terrain roughness",
                "explanation": (
                    "Increase the variance slider. Watch how the terrain surface becomes rougher — "
                    "the Gaussian kernels widen, creating broader, flatter hills. "
                    "Low bandwidth = spiky terrain. High bandwidth = smooth, overfit-prone."
                ),
                "controls": {"variance": 0.8},
                "question": "At what variance does the terrain look most like your mental model of the data?",
            },
            {
                "index": 2,
                "title": "Outliers as canyons",
                "explanation": (
                    "Anomaly points sit far from the main density clusters. "
                    "The gravity-well inversion renders them as glowing canyons rather than peaks. "
                    "This is the predator–prey erosion: outlier points erode the terrain around them."
                ),
                "controls": {"inject_anomaly": True},
                "question": "How many anomaly canyons do you see? How does that map to your outlier count?",
            },
            {
                "index": 3,
                "title": "The water cycle as data lifecycle",
                "explanation": (
                    "Records age out of the active pool (liquefaction → abyss), mutate stochastically, "
                    "evaporate, and re-condense as new data rain. "
                    "This is not metaphor — it is the actual data retention pipeline."
                ),
                "controls": {"steps": 5},
                "question": "After 5 steps, which biomes have changed? What drove those changes?",
            },
            {
                "index": 4,
                "title": "Stability Index — measuring model health",
                "explanation": (
                    "The Stability Index S = ∫ROI(t)dt / TotalEntropy. "
                    "A Stabilized Manifold (S > 0.7) means your interventions successfully "
                    "maintained homeostasis. A Systemic Collapse means the data had too much "
                    "intrinsic chaos for the policy agent to contain."
                ),
                "controls": {},
                "question": "What is your current S score? What does a collapse look like visually?",
            },
        ],
    },
    "fraud-detection-tour": {
        "title": "Fraud Detection with Geo-latent",
        "audience": "Financial risk analysts",
        "steps": [
            {
                "index": 0,
                "title": "Load a transaction dataset",
                "explanation": "Map x=normalised_amount, y=normalised_time_of_day, energy=frequency.",
                "controls": {"scenario": "fraud-aml"},
                "question": "Where do the transaction clusters sit? Are there any obvious outliers?",
            },
            {
                "index": 1,
                "title": "Activate the predator layer",
                "explanation": "Introduce fraud transactions as predator points. Watch them erode legitimate terrain.",
                "controls": {"inflow_mode": "predator"},
                "question": "Which geographic regions show the fastest erosion?",
            },
            {
                "index": 2,
                "title": "Siphon control as AML intervention",
                "explanation": "The siphon beam transfers energy from fraud clusters back to legitimate terrain.",
                "controls": {"siphon_fraction": 0.3},
                "question": "Does the intervention stabilise the manifold? What is the new S score?",
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/tour/{pack_id}")
async def get_tour(pack_id: str):
    pack = _TOUR_PACKS.get(pack_id)
    if not pack:
        raise HTTPException(404, f"Tour '{pack_id}' not found")
    return {"pack_id": pack_id, **pack, "available_packs": list(_TOUR_PACKS.keys())}


@router.post("/tour/{pack_id}/session")
async def start_tour_session(pack_id: str):
    if pack_id not in _TOUR_PACKS:
        raise HTTPException(404, f"Tour '{pack_id}' not found")
    session_id = f"{pack_id}:{int(time.time())}"
    _tours[session_id] = {"pack_id": pack_id, "current_step": 0, "started_at": time.time()}
    pack = _TOUR_PACKS[pack_id]
    return {"session_id": session_id, "first_step": pack["steps"][0]}


@router.post("/tour/{pack_id}/step")
async def advance_tour(pack_id: str, request: Request):
    body = await request.json()
    session_id = body.get("session_id", "")
    session = _tours.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found — call POST /tour/{id}/session first")

    pack = _TOUR_PACKS[pack_id]
    steps = pack["steps"]
    current = session["current_step"]

    # Apply step controls to engine if running
    step_data = steps[current]
    engine = request.app.state.engine
    if engine and step_data.get("controls"):
        try:
            engine.set_controls(step_data["controls"])
            if step_data["controls"].get("steps", 0) > 0:
                for _ in range(step_data["controls"]["steps"]):
                    engine.step_once()
        except Exception:
            pass

    session["current_step"] = min(current + 1, len(steps) - 1)
    next_step = steps[session["current_step"]] if session["current_step"] < len(steps) else None

    return {
        "completed_step": step_data,
        "next_step":       next_step,
        "progress":        f"{session['current_step']}/{len(steps)}",
        "finished":        session["current_step"] >= len(steps) - 1,
    }


@router.get("/worksheet/{run_id}")
async def export_worksheet(run_id: str, request: Request):
    """
    Export a structured markdown worksheet for classroom use.
    Students can answer the embedded questions and submit as evidence.
    """
    engine = request.app.state.engine
    frame  = engine.current_frame() if engine else {}
    report = engine.current_report() if engine else {}
    scene  = engine.current_scene() if engine else {}

    biome_sample = list(scene.get("biomes", {}).values())[:5] if scene.get("biomes") else []

    md = f"""# Geo-latent Analysis Worksheet
**Run ID:** `{run_id}`
**Generated:** {time.strftime("%Y-%m-%d %H:%M UTC")}

---

## Simulation State

| Metric | Value |
|--------|-------|
| Step | {frame.get('step', '—')} |
| Active points | {frame.get('active', '—')} |
| Sea level | {frame.get('sea_level', '—')} |
| Total energy | {frame.get('total_energy', '—')} |

---

## Biome Observations

The terrain currently contains the following biomes:
{chr(10).join(f'- {b}' for b in biome_sample) or '- (Run a simulation first)'}

**Q1.** Which biome dominates the terrain? What feature of your data explains this?

_Answer:_ _______________________________________________

**Q2.** Are any "Fracture Bloom — High-Gradient Drift Zone" biomes present?
If so, which features are competing for dominance?

_Answer:_ _______________________________________________

---

## Anomaly Analysis

**Q3.** How many anomaly canyons (Event Horizon zones) are visible?
Map each to a concrete data point or cluster.

_Answer:_ _______________________________________________

---

## Stability Assessment

Stability Index: **{report.get('stability_index', '—')}**

**Q4.** Is the simulation trending toward "Stabilized Manifold" or "Systemic Collapse"?
What interventions would you apply via the siphon control?

_Answer:_ _______________________________________________

---

## Extension Task

Load a second dataset and activate the Predator–Prey collision scenario.
Document how the Lotka–Volterra dynamics change the biome map after 10 steps.

---
*Generated by Geo-latent v3.0 — Education Tier*
"""
    return {"run_id": run_id, "worksheet_markdown": md, "format": "markdown"}


@router.get("/glossary")
async def glossary():
    """Full terminology reference for students."""
    return {
        "terms": {
            "KDE (Kernel Density Estimation)": "Statistical method that estimates the probability density of a dataset by summing Gaussian kernels centred on each data point.",
            "Biome": "A named terrain region characterised by its local statistical properties (variance, gradient). Geo-latent uses hybrid poetic–scientific naming.",
            "Predator–Prey Erosion": "Competitive terrain dynamics using Lotka–Volterra equations. Predator data points erode the terrain created by prey data points.",
            "Sea Level": "The carrying capacity threshold — data points below sea level are suppressed (liquefied) and enter the abyss pool.",
            "Abyss": "The pool of aged/stale data records. Records undergo stochastic mutation here before potentially evaporating back into the atmosphere.",
            "Immortal Cell": "A grid cell that remains within 1σ of the density mean for 2000+ consecutive ticks — representing a universal truth in the dataset.",
            "Stability Index (S)": "S = ∫ROI(t)dt / TotalEntropy. A score above 0.7 indicates a Stabilized Manifold; below indicates a Systemic Collapse.",
            "Observer Beam": "The user's presence in the simulation. Attention acts as selective pressure — observed regions gain energy.",
            "Siphon": "An operator control that transfers energy from one terrain region to another, used to suppress anomalies or boost weak signals.",
            "Entropy Lightning": "Spawns when Shannon entropy H(X) exceeds the critical threshold — a pruning event that applies Gaussian smoothing to reduce chaos.",
        }
    }


@router.post("/quiz")
async def generate_quiz(request: Request):
    """Auto-generate a multiple-choice quiz from the current simulation state."""
    engine = request.app.state.engine
    frame  = engine.current_frame() if engine else {}
    report = engine.current_report() if engine else {}

    S = report.get("stability_index", 0.75)
    sea = frame.get("sea_level", 0.15)

    questions = [
        {
            "q": "What does a high sea level indicate in the geo-latent simulation?",
            "options": ["A: More data points are active", "B: Carrying capacity is overwhelmed — complexity overflow is occurring", "C: The terrain is more stable", "D: Predator points have won the terrain"],
            "answer": "B",
            "explanation": "Sea level rises when the active pool exceeds carrying capacity, acting as a soft reset to suppress low-relevance data.",
        },
        {
            "q": f"The current Stability Index is {S:.2f}. This means:",
            "options": ["A: All data is corrupt", f"B: The simulation is a {'Stabilized Manifold' if S>0.7 else 'Systemic Collapse'}", "C: The sea level is too low", "D: No interventions have occurred"],
            "answer": "B",
            "explanation": f"S {'> 0.7 → Stabilized Manifold' if S>0.7 else '< 0.7 → Systemic Collapse'}. Interventions {'successfully' if S>0.7 else 'failed to'} maintained homeostasis.",
        },
        {
            "q": "In the predator–prey collision, what happens to a 'prey' data region?",
            "options": ["A: Its energy increases", "B: It gets relabelled as predator", "C: It is eroded by predator energy via Lotka–Volterra dynamics", "D: It evaporates immediately"],
            "answer": "C",
            "explanation": "Predator data points reduce prey terrain energy following dy/dt = δxy − γy, creating visible canyon erosion.",
        },
    ]
    return {"quiz": questions, "generated_at": time.strftime("%Y-%m-%d %H:%M UTC")}


@router.get("/datasets")
async def teaching_datasets():
    """Curated public datasets suitable for classroom use."""
    return {
        "datasets": [
            {
                "name": "Iris Species",
                "url":  "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/iris.csv",
                "cols": {"x": "sepal_length", "y": "sepal_width", "energy": "petal_length"},
                "description": "Classic multi-class dataset. Expect 3 distinct mountain clusters.",
                "audience": "Intro stats",
            },
            {
                "name": "NYC Taxi Trips (sample)",
                "url": "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv",
                "cols": {"x": "Age", "y": "Fare", "energy": "Survived", "kind": "Pclass"},
                "description": "Survival vs demographics. Predator/prey: survivor vs non-survivor terrain.",
                "audience": "Applied ML",
            },
            {
                "name": "Palmer Penguins",
                "url": "https://raw.githubusercontent.com/mwaskom/seaborn-data/master/penguins.csv",
                "cols": {"x": "bill_length_mm", "y": "flipper_length_mm", "energy": "body_mass_g"},
                "description": "Three species form three mountain clusters — ideal for KDE visualisation.",
                "audience": "Data literacy",
            },
        ]
    }
