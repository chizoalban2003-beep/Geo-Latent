"""
geolatent/mesh.py
3-D mesh export — OBJ file + scene JSON for WebGL / Godot / Unity clients.
"""
from __future__ import annotations

import math
import os
from typing import Any

from geolatent.simulator import WorldState


def build_scene(state: WorldState) -> dict:
    """
    Convert WorldState terrain into a scene dict:
      vertices: [[x, y, z], ...]  normalised 0–1
      faces:    [[i, j, k], ...]  triangle indices
      biomes:   {"gx,gy": "label string", ...}
      entities: [{type, x, y, z, label}, ...]
    """
    terrain = state.terrain
    if terrain is None:
        return {"vertices": [], "faces": [], "biomes": {}, "entities": []}

    rows = len(terrain)
    cols = len(terrain[0]) if rows else 0
    if rows == 0 or cols == 0:
        return {"vertices": [], "faces": [], "biomes": {}, "entities": []}

    def _v(r, c):
        v = terrain[r][c] if isinstance(terrain[r], list) else float(terrain[r][c])
        return v

    # Find max height for normalisation
    max_h = max(_v(r, c) for r in range(rows) for c in range(cols)) or 1.0

    # Build vertex grid  — vertex index = r * cols + c
    vertices = []
    for r in range(rows):
        for c in range(cols):
            x = c / max(cols - 1, 1)
            z = r / max(rows - 1, 1)
            y = _v(r, c) / max_h            # height as Y axis
            vertices.append([round(x, 5), round(y, 5), round(z, 5)])

    # Build quad-split triangles
    faces = []
    for r in range(rows - 1):
        for c in range(cols - 1):
            tl = r       * cols + c
            tr = r       * cols + c + 1
            bl = (r + 1) * cols + c
            br = (r + 1) * cols + c + 1
            faces.append([tl, tr, bl])
            faces.append([tr, br, bl])

    # Biome map (string keys for JSON)
    biomes = {}
    for (gx, gy), label in state.biome_map.items():
        biomes[f"{gx},{gy}"] = label

    # Entities: fossils (immortal cell markers), mist, beacons
    entities = _build_entities(state)

    return {
        "grid_w":   cols,
        "grid_h":   rows,
        "vertices": vertices,
        "faces":    faces,
        "biomes":   biomes,
        "entities": entities,
    }


def _build_entities(state: WorldState) -> list:
    entities = []
    cols = state.grid_w
    rows = state.grid_h

    # Immortal cell fossils
    for (gx, gy), ticks in state.immortal_candidates.items():
        if ticks >= 500:           # show at 500 as "emerging" fossils
            x = gx / max(cols - 1, 1)
            z = gy / max(rows - 1, 1)
            h = 0.0
            if state.terrain and len(state.terrain) > gy and len(state.terrain[gy]) > gx:
                row = state.terrain[gy]
                raw = row[gx] if isinstance(row, list) else float(row[gx])
                h   = raw
            entities.append({
                "type":  "fossil",
                "x":     round(x, 4),
                "y":     round(h, 4),
                "z":     round(z, 4),
                "label": f"Fossil ({gx},{gy}) — {ticks} ticks",
                "ticks": ticks,
            })

    # Mist / atmosphere particles (sampled)
    for i, pt in enumerate(state.atmosphere[:20]):
        entities.append({
            "type":  "mist",
            "x":     round(pt.x, 4),
            "y":     round(min(1.0, pt.energy / 3.0 + 0.5), 4),
            "z":     round(pt.y, 4),
            "label": f"Mist particle {i}",
            "energy": round(pt.energy, 4),
        })

    return entities


def write_obj(state: WorldState, path: str) -> str:
    """
    Write an OBJ file of the current terrain to `path`.
    Returns the absolute path written.
    """
    scene = build_scene(state)
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)

    lines = [
        "# Geo-latent terrain export",
        f"# Step {state.step}",
        f"# Grid {state.grid_w}x{state.grid_h}",
        "",
    ]
    for v in scene["vertices"]:
        lines.append(f"v {v[0]} {v[1]} {v[2]}")
    lines.append("")
    for f in scene["faces"]:
        # OBJ is 1-indexed
        lines.append(f"f {f[0]+1} {f[1]+1} {f[2]+1}")

    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    return os.path.abspath(path)
