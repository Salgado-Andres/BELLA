"""3D viz renderer — builds the payload and writes a self-contained HTML.

Design (mirrors `bellamem render` for the 2D graphviz path):

  1. build_payload(bella) — pure data transform. Walks the forest,
     collects beliefs + embeddings, reduces embeddings to 2D via UMAP,
     normalizes coordinates, and returns a JSON-serialisable dict.
     This is the data contract the HTML template consumes.

  2. render_html(bella, out_path) — loads the HTML template from
     package data, inlines the JSON payload, writes the result.
     Self-contained output — Three.js is pulled from CDN at open time,
     no build step, no server.

The Python layer precomputes UMAP so the snapshot view is honest
("forest is truth" invariant — layout is part of the observation).
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from ..core.gene import REL_CAUSE, REL_COUNTER, REL_SUPPORT

if TYPE_CHECKING:
    from ..core.bella import Bella


# Distinct field colors. Fifteen is enough for a long time; anything
# beyond that is extremely rare and falls through to a deterministic
# hash-derived color so fields still get stable colors across runs.
_FIELD_PALETTE = [
    "#4c9aff", "#ff6b6b", "#51cf66", "#ffd43b", "#cc5de8",
    "#ff922b", "#22b8cf", "#845ef7", "#f06595", "#94d82d",
    "#339af0", "#fa5252", "#20c997", "#fab005", "#be4bdb",
]


def _color_for(field_name: str, idx: int) -> str:
    if idx < len(_FIELD_PALETTE):
        return _FIELD_PALETTE[idx]
    h = abs(hash(field_name)) & 0xFFFFFF
    return f"#{h:06x}"


def _compute_umap(embeddings: list[list[float]]) -> list[list[float]]:
    """Reduce embeddings to 2D. Deterministic via random_state.

    Tiny forests (< 10 beliefs) use a trivial first-two-dims fallback
    because UMAP is unstable at that size. The fallback is not
    meaningful as a semantic projection — it just keeps render_html
    working on empty/near-empty graphs.
    """
    n = len(embeddings)
    if n == 0:
        return []
    if n < 10:
        return [[float(v[0]) if len(v) > 0 else 0.0,
                 float(v[1]) if len(v) > 1 else 0.0]
                for v in embeddings]
    try:
        import numpy as np
        import umap  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "3D viz requires the 'viz3d' extra. Install with one of:\n"
            "  pipx inject bellamem 'umap-learn>=0.5' 'numpy>=1.21'\n"
            "  pip install 'bellamem[viz3d]'"
        ) from e
    arr = np.asarray(embeddings, dtype=np.float32)
    reducer = umap.UMAP(
        n_components=2,
        random_state=42,
        n_neighbors=min(15, n - 1),
        min_dist=0.1,
    )
    coords = reducer.fit_transform(arr)
    return coords.tolist()


def _normalize_coords(coords: list[list[float]],
                      extent: float = 30.0) -> list[list[float]]:
    """Center coords at origin and scale to fit in a square of side `extent`."""
    if not coords:
        return coords
    xs = [p[0] for p in coords]
    ys = [p[1] for p in coords]
    cx = (min(xs) + max(xs)) / 2
    cy = (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
    k = extent / span
    return [[(p[0] - cx) * k, (p[1] - cy) * k] for p in coords]


def _edge_type_for_rel(rel: str) -> str:
    """Map a bellamem relation constant to a viz edge type string."""
    if rel == REL_CAUSE:
        return "cause"
    if rel == REL_COUNTER:
        return "counter"
    return "support"  # REL_SUPPORT and any unknown relation


def build_payload(bella: "Bella") -> dict:
    """Build the JSON payload the Three.js viz consumes.

    Shape:
      {
        "meta": { "beliefs": N, "fields": K },
        "fields": [ { name, color, belief_count } ],
        "beliefs": [ {
            id, field, desc, mass, voices, parent,
            pos: [x, y],   # UMAP-reduced, normalized
            z: float,      # == mass, kept as its own key so the viz
                           # can swap it for other height metrics later
        } ],
        "edges": [ { type: "support"|"cause"|"counter", from, to } ]
      }
    """
    rows: list[tuple[str, str, object]] = []  # (field, id, belief)
    embeddings: list[list[float]] = []
    fields_meta: list[dict] = []

    for idx, (fname, g) in enumerate(sorted(bella.fields.items())):
        fields_meta.append({
            "name": fname,
            "color": _color_for(fname, idx),
            "belief_count": len(g.beliefs),
        })
        for bid, b in g.beliefs.items():
            rows.append((fname, bid, b))
            # Fall back to a zero vector if an embedding is missing —
            # shouldn't happen with the normal ingest path, but the
            # viz must not crash on a legacy snapshot.
            embeddings.append(b.embedding or [])

    # UMAP needs vectors of uniform length; pad any stragglers to the
    # modal dimensionality.
    if embeddings:
        dim = max(len(v) for v in embeddings) or 2
        embeddings = [
            list(v) + [0.0] * (dim - len(v)) if len(v) < dim else list(v)
            for v in embeddings
        ]

    coords = _normalize_coords(_compute_umap(embeddings))

    beliefs_payload: list[dict] = []
    live_ids: set[str] = set()
    for (fname, bid, b), pos in zip(rows, coords):
        live_ids.add(bid)
        n_voices = int(getattr(b, "n_voices", 0)) or len(getattr(b, "voices", []) or [])
        beliefs_payload.append({
            "id": bid,
            "field": fname,
            "desc": (b.desc or "")[:240],
            "mass": float(b.mass),
            "voices": max(n_voices, 1),
            "parent": b.parent,
            "pos": [float(pos[0]), float(pos[1])],
            "z": float(b.mass),
        })

    # Edges. Every non-root belief has exactly one (parent, rel) edge.
    # We emit it only if both endpoints are in live_ids — keeps the
    # payload consistent when a snapshot has dangling parents (legacy
    # scrubbed graphs occasionally do).
    edges_payload: list[dict] = []
    for fname, g in bella.fields.items():
        for bid, b in g.beliefs.items():
            if b.parent and b.parent in live_ids and bid in live_ids:
                edges_payload.append({
                    "type": _edge_type_for_rel(b.rel),
                    "from": b.parent,
                    "to": bid,
                })

    return {
        "meta": {
            "beliefs": len(beliefs_payload),
            "fields": len(fields_meta),
        },
        "fields": fields_meta,
        "beliefs": beliefs_payload,
        "edges": edges_payload,
    }


def _load_template() -> str:
    """Read the HTML template from package data."""
    from importlib.resources import files
    return (files("bellamem.viz") / "template.html").read_text(encoding="utf-8")


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("bellamem")
    except Exception:
        return "unknown"


def render_html(bella: "Bella", out_path: str) -> int:
    """Write a self-contained HTML file containing the 3D viz.

    Returns the number of beliefs rendered. The output is a single file:
    Three.js is loaded from CDN at open time, no local assets needed.
    """
    payload = build_payload(bella)
    data_json = json.dumps(payload, separators=(",", ":"))

    template = _load_template()
    html = (template
            .replace("{{DATA_JSON}}", data_json)
            .replace("{{BELIEFS}}", str(payload["meta"]["beliefs"]))
            .replace("{{FIELDS}}", str(payload["meta"]["fields"]))
            .replace("{{BELLAMEM_VERSION}}", _get_version()))

    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    return int(payload["meta"]["beliefs"])
