"""
geolatent/visualization.py
ASCII terrain renderer for fast iteration in terminal.
"""
from __future__ import annotations

CHARS = " ·:;+=xX$&#@"


def render_ascii(terrain, sea_level: float = 0.15, width: int = 80) -> str:
    """Return an ASCII string rendering of the terrain grid."""
    if not terrain:
        return "(empty terrain)"

    rows = len(terrain)
    cols = len(terrain[0]) if rows else 0
    if cols == 0:
        return "(empty terrain)"

    flat = [v for row in terrain
            for v in (row if isinstance(row, list) else row.tolist())]
    mn, mx = min(flat), max(flat)
    rng = max(mx - mn, 1e-9)
    sea_norm = (sea_level - mn) / rng if mn <= sea_level <= mx else sea_level

    lines = []
    for r in range(rows):
        line = ""
        for c in range(cols):
            v = terrain[r][c] if isinstance(terrain[r], list) else float(terrain[r][c])
            norm = (v - mn) / rng
            if norm < sea_norm:
                line += "~"
            else:
                idx = min(len(CHARS) - 1, int(norm * len(CHARS)))
                line += CHARS[idx]
        lines.append(line)

    # Add a simple HUD
    lines.append(f"sea={sea_level:.2f}  range=[{mn:.2f}, {mx:.2f}]  {cols}x{rows}")
    return "\n".join(lines)
