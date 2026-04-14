"""Graphviz-backed 2D static renderer for v0.2 graph.

Builds a DOT document from a filtered VizPayload and shells out to
graphviz (via the `graphviz` Python bindings, declared as the `[viz]`
extra) to emit SVG, PNG, or raw DOT text.

Layout strategy: one cluster subgraph per populated class × nature
cell, concepts grouped inside their cluster, static cross-edges
(support/dispute/cause/elaborate) drawn between clusters. Event
edges (voice-cross / retract / consume-*) are transcoded into node
decorations because a static view has no playhead.

See `bellamem/proto/VIZ_DESIGN.md` §2D for the visual contract.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional

from bellamem.proto.graph import Graph
from bellamem.proto.schema import Concept, Edge
from bellamem.proto.viz import Filters, VizPayload, build_payload, ephemeral_decoration


# Class hue — base color for each epistemic class. Saturation/outline
# is modulated further by nature.
_CLASS_HUE = {
    "invariant":   {"deep": "#1e3a8a", "mid": "#3b82f6", "pale": "#dbeafe"},
    "decision":    {"deep": "#9a3412", "mid": "#f97316", "pale": "#ffedd5"},
    "observation": {"deep": "#374151", "mid": "#9ca3af", "pale": "#f3f4f6"},
    "ephemeral":   {"deep": "#14532d", "mid": "#22c55e", "pale": "#dcfce7"},
}

# Nature → saturation bucket inside its class hue.
_NATURE_BUCKET = {
    "metaphysical": "deep",
    "normative":    "mid",
    "factual":      "pale",
}

# Outline color modifier by nature (warm vs cool vs none).
_NATURE_OUTLINE = {
    "metaphysical": "#b45309",  # warm amber — "what the system IS"
    "normative":    "#0369a1",  # cool slate-blue — "what we commit to"
    "factual":      None,        # no outline
}

# Edge type → graphviz attribute dict.
_EDGE_STYLE = {
    "support":   {"color": "#94a3b8", "penwidth": "0.6", "arrowhead": "none"},
    "elaborate": {"color": "#22c55e", "style": "dashed", "arrowhead": "normal"},
    "cause":     {"color": "#06b6d4", "penwidth": "1.2", "arrowhead": "normal"},
    "dispute":   {"color": "#ef4444", "penwidth": "1.8", "style": "bold", "arrowhead": "none"},
}

# Display order for clusters. Blue (invariant) anchors the top; green
# (ephemeral) lives in its own row so in-progress work is visually
# segregated from ratified content.
_CLASS_ORDER = ["invariant", "decision", "observation", "ephemeral"]
_NATURE_ORDER = ["metaphysical", "normative", "factual"]


def _wrap_label(topic: str, width: int = 20) -> str:
    """Wrap topic to ~width-char lines for readability inside a node."""
    wrapped = textwrap.wrap(topic, width=width, break_long_words=False)
    # graphviz escapes: use \n literal (not real newline) inside the label
    return "\\n".join(wrapped) if wrapped else topic


def _node_attrs(c: Concept) -> dict[str, str]:
    hue = _CLASS_HUE[c.class_]
    bucket = _NATURE_BUCKET[c.nature]
    fill = hue[bucket]
    # Pale fills need dark text; deep/mid fills need white text.
    fontcolor = "#0f172a" if bucket == "pale" else "#ffffff"
    attrs: dict[str, str] = {
        "shape": "circle",
        "style": "filled",
        "fillcolor": fill,
        "fontcolor": fontcolor,
        # Mass maps to font size: 12pt at m=0.5, 20pt at m=1.0.
        "fontsize": f"{12 + 8 * max(0.0, min(1.0, c.mass)):.1f}",
        "fontname": "Helvetica",
        "width": f"{0.55 + 0.8 * c.mass:.2f}",
        "fixedsize": "false",
    }
    outline = _NATURE_OUTLINE[c.nature]
    if outline is not None:
        attrs["color"] = outline
        attrs["penwidth"] = "2.0"
    else:
        attrs["color"] = "#e5e7eb"
        attrs["penwidth"] = "0.5"

    # Ephemeral state decorations override style where needed.
    if c.class_ == "ephemeral":
        if c.state == "retracted":
            attrs["style"] = "filled,dashed"
            attrs["color"] = "#dc2626"
            attrs["penwidth"] = "2.0"
        elif c.state == "stale":
            attrs["fillcolor"] = "#e5e7eb"
            attrs["fontcolor"] = "#6b7280"
            attrs["color"] = "#9ca3af"
    return attrs


def _escape(s: str) -> str:
    """Minimal graphviz label escaping. We emit labels between "…"
    so we only need to escape backslashes and double-quotes. Literal
    \\n sequences produced by _wrap_label must survive."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\\\\n", "\\n")


def _node_id(cid: str) -> str:
    """Sanitize a concept id for use as a DOT node id. Concepts are
    already slug-shaped but DOT wants bare identifiers — quote and
    escape to be safe."""
    return '"c_' + cid.replace('"', '\\"') + '"'


def _cluster_label(class_: str, nature: str, n: int) -> str:
    return f"{class_} × {nature}   ({n})"


def build_dot(payload: VizPayload) -> str:
    """Render the payload as DOT source text."""
    lines: list[str] = []
    lines.append("digraph bella_v02 {")
    lines.append('  rankdir="TB";')
    lines.append('  compound=true;')
    lines.append('  splines=curved;')
    lines.append('  overlap=false;')
    lines.append('  bgcolor="#ffffff";')
    lines.append('  fontname="Helvetica";')
    lines.append('  node [fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica"];')
    lines.append("")

    # Group kept concepts by (class, nature).
    cells: dict[tuple[str, str], list[Concept]] = {}
    for c in payload.concepts:
        cells.setdefault((c.class_, c.nature), []).append(c)

    # Emit one cluster per populated cell, in stable order.
    cluster_idx = 0
    for class_ in _CLASS_ORDER:
        for nature in _NATURE_ORDER:
            key = (class_, nature)
            members = cells.get(key)
            if not members:
                continue
            hue = _CLASS_HUE[class_]["pale"]
            border = _CLASS_HUE[class_]["mid"]
            lines.append(f"  subgraph cluster_{cluster_idx} {{")
            lines.append(f'    label="{_cluster_label(class_, nature, len(members))}";')
            lines.append(f'    style="filled,rounded";')
            lines.append(f'    fillcolor="{hue}";')
            lines.append(f'    color="{border}";')
            lines.append(f'    fontcolor="#0f172a";')
            lines.append(f'    fontsize="11";')
            lines.append(f'    labeljust="l";')
            lines.append(f'    margin="12";')
            # Members sorted by mass descending for within-cluster stacking.
            for c in sorted(members, key=lambda x: (-x.mass, x.topic)):
                attrs = _node_attrs(c)
                label = _wrap_label(c.topic) + ephemeral_decoration(c)
                attr_str = ", ".join(
                    f'{k}="{_escape(v)}"' for k, v in attrs.items()
                )
                lines.append(
                    f'    {_node_id(c.id)} [label="{_escape(label)}", {attr_str}];'
                )
            lines.append("  }")
            lines.append("")
            cluster_idx += 1

    # Cross-edges. Edges live at top-level (not inside a cluster) so
    # graphviz routes them across cluster boundaries cleanly.
    for e in payload.edges:
        style = _EDGE_STYLE.get(e.type, {})
        attr_str = ", ".join(f'{k}="{v}"' for k, v in style.items())
        lines.append(
            f"  {_node_id(e.source)} -> {_node_id(e.target)} [{attr_str}];"
        )

    lines.append("}")
    return "\n".join(lines) + "\n"


def render(
    graph: Graph,
    out_path: Path,
    *,
    filters: Optional[Filters] = None,
    format: Optional[str] = None,
    engine: str = "dot",
) -> VizPayload:
    """Build the payload, produce DOT, and write the requested format.

    `format` defaults to the out_path suffix ("svg", "png", "dot").
    Returns the VizPayload so callers can log counts.
    """
    payload = build_payload(graph, filters)
    dot_text = build_dot(payload)

    out_path = Path(out_path)
    fmt = (format or out_path.suffix.lstrip(".") or "svg").lower()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "dot":
        out_path.write_text(dot_text, encoding="utf-8")
        return payload

    rendered_bytes = _run_graphviz(dot_text, engine=engine, fmt=fmt)
    out_path.write_bytes(rendered_bytes)
    return payload


def _run_graphviz(dot_text: str, *, engine: str, fmt: str) -> bytes:
    """Render DOT to the requested format.

    Prefers the `graphviz` Python binding (declared as the `[viz]`
    extra) but falls back to shelling out to the `dot` binary when
    the binding isn't installed — most Linux boxes ship `dot` via the
    system package manager even without the Python wrapper.
    """
    try:
        from graphviz import Source  # type: ignore

        src = Source(dot_text, engine=engine, format=fmt)
        return src.pipe()
    except ImportError:
        pass

    import shutil
    import subprocess

    if shutil.which(engine) is None:
        raise RuntimeError(
            f"graphviz not available: neither the Python binding "
            f"(`pip install bellamem[viz]`) nor the `{engine}` binary "
            f"(e.g. `apt install graphviz`) is installed"
        )
    proc = subprocess.run(
        [engine, f"-T{fmt}"],
        input=dot_text.encode("utf-8"),
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{engine} failed (exit {proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace')}"
        )
    return proc.stdout
