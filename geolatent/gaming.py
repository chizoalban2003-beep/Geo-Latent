"""
geolatent/gaming.py
Gaming & Entertainment infrastructure layer.

Exposes:
  GET  /gaming/world            — current world state (Godot-friendly JSON)
  GET  /gaming/world_seed       — generate a world from a public dataset URL
  POST /gaming/player_move      — WASD observer beam control (player character)
  GET  /gaming/players          — all active player beams (multiplayer registry)
  GET  /gaming/biome_at/{x}/{y} — biome label at normalised coordinates
  GET  /gaming/leaderboard      — stability scores ranked by player
  WS   /gaming/ws               — low-latency game loop WebSocket (50 ms ticks)
  GET  /gaming/godot_schema     — GDScript integration contract
  GET  /gaming/unity_schema     — Unity C# integration contract
"""
from __future__ import annotations

import json
import math
import os
import time
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends, HTTPException

router = APIRouter()


# ---------------------------------------------------------------------------
# In-memory player registry  (per-process; use Redis for multi-pod deploys)
# ---------------------------------------------------------------------------

_players: dict[str, dict] = {}   # player_id → {x, y, radius, score, name, ts}
_PLAYER_TTL = 60.0               # seconds before a player is considered disconnected


def _prune_players():
    now = time.time()
    dead = [pid for pid, p in _players.items() if now - p["ts"] > _PLAYER_TTL]
    for pid in dead:
        del _players[pid]


# ---------------------------------------------------------------------------
# Helper: engine from request state
# ---------------------------------------------------------------------------

def _get_engine(request: Request):
    engine = request.app.state.engine
    if engine is None:
        raise HTTPException(503, "Simulation not running")
    return engine


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/world")
async def get_world(request: Request):
    """
    Full world state optimised for game engine consumption.
    Includes terrain mesh, biomes, entities, sea level, active anomalies.
    """
    engine = _get_engine(request)
    frame  = engine.current_frame()
    scene  = engine.current_scene()
    return {
        "step":       frame.get("step", 0),
        "sea_level":  frame.get("sea_level", 0.15),
        "terrain":    scene.get("vertices", []),
        "faces":      scene.get("faces", []),
        "biomes":     scene.get("biomes", {}),
        "entities":   scene.get("entities", []),
        "anomalies":  _extract_anomalies(frame),
        "players":    list(_players.values()),
        "ts":         time.time(),
    }


@router.get("/world_seed")
async def world_seed(dataset: Optional[str] = None):
    """
    Generate a world seed descriptor from a named public dataset.
    The seed tells the engine which inflow scenario to use.
    Partners: GDELT (geopolitics), OpenAQ (air quality), Kaggle public.
    """
    _SEEDS = {
        "gdelt":     {"scenario": "neutral-baseline", "label": "Global Events (GDELT)", "description": "Real-time geopolitical event density mapped to terrain elevation."},
        "openaq":    {"scenario": "neutral-baseline", "label": "Air Quality (OpenAQ)",  "description": "Particulate matter PM2.5 readings across global monitoring stations."},
        "finance":   {"scenario": "fraud-aml",        "label": "Financial Transactions","description": "Transaction velocity and anomaly density — fraud clusters become canyons."},
        "climate":   {"scenario": "neutral-baseline", "label": "Climate Indicators",    "description": "Temperature anomaly and CO₂ concentration over a 30-year window."},
        "sports":    {"scenario": "predator-prey",    "label": "Sports Match Events",   "description": "Attacking vs defensive play events compete for terrain dominance."},
        "social":    {"scenario": "predator-prey",    "label": "Social Media Signals",  "description": "Trending vs counter-trending content ecosystems."},
    }
    if dataset and dataset in _SEEDS:
        seed = _SEEDS[dataset]
        return {"seed": seed, "dataset": dataset}
    return {"available_seeds": list(_SEEDS.keys()), "usage": "GET /gaming/world_seed?dataset=gdelt"}


@router.post("/player_move")
async def player_move(request: Request):
    """
    WASD / joystick observer beam movement.
    Body: {player_id, name, x, y, radius, pressure}
    Moves the observer beam and returns the immediately affected frame slice.
    """
    body = await request.json()
    player_id = body.get("player_id") or str(uuid.uuid4())
    x         = float(body.get("x", 0.5))
    y         = float(body.get("y", 0.5))
    radius    = float(body.get("radius", 0.1))
    pressure  = float(body.get("pressure", 0.1))

    _players[player_id] = {
        "player_id": player_id,
        "name":      body.get("name", f"Player-{player_id[:6]}"),
        "x":         x,
        "y":         y,
        "radius":    radius,
        "pressure":  pressure,
        "score":     _players.get(player_id, {}).get("score", 0),
        "ts":        time.time(),
    }
    _prune_players()

    engine = _get_engine(request)
    try:
        engine.set_observer(x, y, radius)
    except Exception:
        pass

    return {
        "player_id": player_id,
        "position":  {"x": x, "y": y, "radius": radius},
        "players_online": len(_players),
    }


@router.get("/players")
async def get_players():
    """All currently active players — useful for multiplayer HUD."""
    _prune_players()
    return {"players": list(_players.values()), "count": len(_players)}


@router.get("/biome_at/{x}/{y}")
async def biome_at(x: float, y: float, request: Request):
    """Return the biome label at normalised coordinates (0.0–1.0)."""
    engine = _get_engine(request)
    try:
        scene = engine.current_scene()
        biomes = scene.get("biomes", {})
        state = engine.state if hasattr(engine, "state") else None
        if state:
            gx = int(x * state.grid_w)
            gy = int(y * state.grid_h)
            key = f"{gx},{gy}"
            label = biomes.get(key) or biomes.get((gx, gy), "Unknown biome")
        else:
            label = "Simulation not loaded"
    except Exception:
        label = "Unknown biome"
    return {"x": x, "y": y, "biome": label}


@router.get("/leaderboard")
async def leaderboard():
    """Stability contribution scores per player."""
    _prune_players()
    ranked = sorted(_players.values(), key=lambda p: p.get("score", 0), reverse=True)
    return {"leaderboard": ranked[:20]}


@router.post("/score")
async def update_score(request: Request):
    """Update a player's stability contribution score."""
    body = await request.json()
    pid = body.get("player_id", "")
    if pid in _players:
        _players[pid]["score"] = float(body.get("score", 0))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Low-latency game loop WebSocket
# ---------------------------------------------------------------------------

@router.websocket("/ws")
async def game_ws(websocket: WebSocket):
    """
    Game loop WebSocket — 50 ms ticks.
    Client sends: {type: "move", player_id, x, y, radius}
    Server pushes: {type: "world", step, terrain_hash, sea_level, anomalies, players}
    """
    await websocket.accept()
    player_id = str(uuid.uuid4())
    await websocket.send_json({"type": "connected", "player_id": player_id})

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break

            if data.get("type") == "move":
                x = float(data.get("x", 0.5))
                y = float(data.get("y", 0.5))
                r = float(data.get("radius", 0.1))
                _players[player_id] = {
                    "player_id": player_id,
                    "name": data.get("name", f"P-{player_id[:6]}"),
                    "x": x, "y": y, "radius": r,
                    "pressure": float(data.get("pressure", 0.1)),
                    "score": _players.get(player_id, {}).get("score", 0),
                    "ts": time.time(),
                }
                engine = websocket.app.state.engine
                if engine:
                    try:
                        engine.set_observer(x, y, r)
                        frame = engine.current_frame()
                        await websocket.send_json({
                            "type":       "world",
                            "step":       frame.get("step", 0),
                            "sea_level":  frame.get("sea_level", 0.15),
                            "anomalies":  _extract_anomalies(frame),
                            "players":    len(_players),
                        })
                    except Exception:
                        pass

            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})

    finally:
        _players.pop(player_id, None)
        _prune_players()


# ---------------------------------------------------------------------------
# SDK schema — integration contracts for game engines
# ---------------------------------------------------------------------------

@router.get("/godot_schema")
async def godot_schema():
    """
    GDScript integration contract.
    Drop this into your Godot project to connect to the live terrain stream.
    """
    return {
        "engine":   "Godot 4.x",
        "protocol": "WebSocket",
        "url":      "/gaming/ws",
        "gdscript_snippet": """
# geo_latent_client.gd
extends Node

var ws := WebSocketPeer.new()
var player_id := ""

func _ready():
    ws.connect_to_url("ws://YOUR_SERVER:PORT/gaming/ws")

func _process(_delta):
    ws.poll()
    if ws.get_ready_state() == WebSocketPeer.STATE_OPEN:
        while ws.get_available_packet_count() > 0:
            var msg = JSON.parse_string(ws.get_packet().get_string_from_utf8())
            if msg.type == "connected":
                player_id = msg.player_id
            elif msg.type == "world":
                update_terrain(msg)

func move(x: float, y: float, radius: float = 0.1):
    var payload = JSON.stringify({
        "type": "move", "player_id": player_id,
        "x": x, "y": y, "radius": radius
    })
    ws.send_text(payload)

func update_terrain(world_data: Dictionary):
    # world_data.step, world_data.sea_level, world_data.anomalies
    pass  # Wire to your MeshInstance3D here
""",
        "rest_endpoints": {
            "world":       "GET /gaming/world       — full terrain JSON",
            "biome_at":    "GET /gaming/biome_at/{x}/{y}",
            "leaderboard": "GET /gaming/leaderboard",
            "world_seed":  "GET /gaming/world_seed?dataset=gdelt",
        },
        "terrain_format": {
            "vertices": "list of [x, y, z] floats, normalised 0–1",
            "faces":    "list of [i, j, k] vertex indices",
            "biomes":   "dict of 'gx,gy' → biome label string",
        },
    }


@router.get("/unity_schema")
async def unity_schema():
    """C# Unity integration contract."""
    return {
        "engine":   "Unity 2022+",
        "protocol": "REST polling + WebSocket",
        "polling_endpoint": "/sdk/exports/latest",
        "polling_interval_ms": 100,
        "csharp_snippet": """
// GeoLatentClient.cs
using UnityEngine;
using System.Net.Http;
using System.Threading.Tasks;
using Newtonsoft.Json.Linq;

public class GeoLatentClient : MonoBehaviour {
    private static readonly HttpClient _http = new();
    private const string BASE = "http://YOUR_SERVER:PORT";
    private const string TOKEN = "YOUR_JWT_HERE";

    async void Start() {
        _http.DefaultRequestHeaders.Add("Authorization", $"Bearer {TOKEN}");
        await PollLoop();
    }

    async Task PollLoop() {
        while (true) {
            var resp = await _http.GetStringAsync($"{BASE}/sdk/exports/latest");
            var data = JObject.Parse(resp);
            ApplyTerrain(data["scene"]);
            await Task.Delay(100);
        }
    }

    void ApplyTerrain(JToken scene) {
        // scene["vertices"] → List<Vector3>
        // scene["faces"]    → List<int[]>
        // scene["biomes"]   → Dictionary<string, string>
    }
}
""",
    }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _extract_anomalies(frame: dict) -> list:
    """Pull anomaly coordinates from frame metrics."""
    return frame.get("anomalies", []) or []
