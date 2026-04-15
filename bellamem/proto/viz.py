"""Shared payload transform for v0.2 graph visualization.

`viz_2d` (graphviz SVG) and a future `viz_3d` (Three.js) both start
from the filtered payload built here. Keeping the filter and
class/nature/state/depth computation in one place means the two
rendering formats stay consistent without duplicating selection
logic.

See `bellamem/proto/VIZ_DESIGN.md` for the design spec.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from bellamem.proto.graph import Graph
from bellamem.proto.schema import Concept, Edge, Source


# Edge types that survive into the static cc (concept↔concept) view.
# These are the first-class structural relationships between concepts.
STATIC_EDGE_TYPES = frozenset({"support", "dispute", "cause", "elaborate"})

# Edge types that count as hyperedge spokes in the bipartite view.
# Any turn→concept edge in this set contributes to the hub-degree
# of its originating turn. Includes event-style edges (voice-cross,
# consume-*, retract) because those ARE co-citation signals even
# though they don't render as concept↔concept lines.
HYPEREDGE_TYPES = frozenset({
    "support", "dispute", "cause", "elaborate",
    "voice-cross", "retract", "consume-success", "consume-failure",
})


@dataclass
class Filters:
    min_mass: float = 0.55
    classes: Optional[frozenset[str]] = None
    states: Optional[frozenset[str]] = None  # None = ephemeral-state filter off
    session: Optional[str] = None
    max_concepts: Optional[int] = None
    expand_edge_partners: bool = True  # pull in low-mass neighbors of kept concepts
    include_turn_hubs: bool = True     # bipartite hyperedge rendering
    min_turn_degree: int = 3           # a turn is a hyperedge iff it touches ≥N concepts


@dataclass
class VizPayload:
    concepts: list[Concept]
    edges: list[Edge]            # concept→concept structural edges (cc)
    depths: dict[str, int]
    n_total_concepts: int
    n_total_edges: int
    class_counts: dict[str, int]
    nature_counts: dict[str, int]
    filters: Filters
    turns: list[Source] = None   # turn-hub sources (for bipartite hyperedge mode)
    turn_edges: list[Edge] = None  # turn→concept edges from qualifying turns

    def __post_init__(self) -> None:
        if self.turns is None:
            self.turns = []
        if self.turn_edges is None:
            self.turn_edges = []


def _tree_depth(concepts: dict[str, Concept], cid: str) -> int:
    """Chain length up to a parentless root. Cycles/missing parents
    terminate the walk safely."""
    depth = 0
    seen = {cid}
    current = concepts.get(cid)
    while current is not None and current.parent:
        parent_id = current.parent
        if parent_id in seen or parent_id not in concepts:
            break
        seen.add(parent_id)
        depth += 1
        current = concepts[parent_id]
    return depth


def _concept_in_session(c: Concept, session: str) -> bool:
    for sr in c.source_refs:
        if sr.split("#", 1)[0] == session:
            return True
    return False


def build_payload(graph: Graph, filters: Optional[Filters] = None) -> VizPayload:
    """Apply filters and materialize the render-ready payload.

    Filtering rules:
      - `min_mass` drops low-mass concepts (default 0.55 keeps R1-boosted).
      - `classes` restricts to one or more of invariant/decision/observation/ephemeral.
      - `states` restricts ephemeral state (None = include all; non-ephemerals bypass).
      - `session` keeps only concepts cited in that session at least once.
      - Edges are filtered to STATIC_EDGE_TYPES and only those whose
        both endpoints survived concept filtering.
      - `max_concepts` truncates by mass descending after the above.
    """
    filters = filters or Filters()

    kept: list[Concept] = []
    for c in graph.concepts.values():
        if c.mass < filters.min_mass:
            continue
        if filters.classes is not None and c.class_ not in filters.classes:
            continue
        if filters.states is not None:
            if c.class_ == "ephemeral" and c.state not in filters.states:
                continue
        if filters.session is not None and not _concept_in_session(c, filters.session):
            continue
        kept.append(c)

    kept.sort(key=lambda c: (-c.mass, -len(c.source_refs), c.topic))
    if filters.max_concepts is not None and len(kept) > filters.max_concepts:
        kept = kept[: filters.max_concepts]

    kept_ids = {c.id for c in kept}

    # Edge-partner expansion: always include concepts that participate
    # in a concept→concept structural edge, regardless of mass. At
    # current R1 calibration, the high-mass concepts and the
    # structurally-connected concepts are mostly disjoint populations
    # (most cc-edges live at the m=0.5 floor because only one voice
    # has ratified them). Without this expansion, a mass-filtered view
    # would show zero edges, which hides the graph's actual structure.
    # Union of the two populations is the honest default.
    if filters.expand_edge_partners:
        for e in graph.edges.values():
            if e.type not in STATIC_EDGE_TYPES:
                continue
            if e.source not in graph.concepts or e.target not in graph.concepts:
                continue  # turn→concept edges — not structural
            for pid in (e.source, e.target):
                if pid in kept_ids:
                    continue
                partner = graph.concepts[pid]
                if filters.classes is not None and partner.class_ not in filters.classes:
                    continue
                if filters.session is not None and not _concept_in_session(partner, filters.session):
                    continue
                kept.append(partner)
                kept_ids.add(pid)

    depths = {c.id: _tree_depth(graph.concepts, c.id) for c in kept}

    kept_edges: list[Edge] = []
    for e in graph.edges.values():
        if e.type not in STATIC_EDGE_TYPES:
            continue
        if e.source not in kept_ids or e.target not in kept_ids:
            continue
        kept_edges.append(e)

    # Bipartite hyperedge expansion: a turn is a hub iff it cites
    # ≥N distinct concepts. Ground truth for "which turns touch
    # which concepts" lives in `concept.source_refs` — graph.edges
    # only captures ~65% of those citations as explicit Edge
    # objects. Iterating source_refs gives full coverage. When an
    # explicit Edge exists we preserve its type; otherwise the
    # spoke is a generic "cite" hyperedge.
    turn_hubs: list[Source] = []
    turn_edges: list[Edge] = []
    if filters.include_turn_hubs:
        # Ground-truth turn → concept map from source_refs.
        turn_to_targets: dict[str, set[str]] = {}
        for c in graph.concepts.values():
            for sr in c.source_refs:
                turn_to_targets.setdefault(sr, set()).add(c.id)

        # Index explicit turn→concept Edges by (turn_id, concept_id)
        # so we can look up the edge type when synthesizing spokes.
        edge_by_pair: dict[tuple[str, str], Edge] = {}
        for e in graph.edges.values():
            if e.type not in HYPEREDGE_TYPES:
                continue
            if e.source in graph.concepts:
                continue
            if e.target not in graph.concepts:
                continue
            edge_by_pair[(e.source, e.target)] = e

        hub_partners: set[str] = set()
        for turn_id, targets in turn_to_targets.items():
            if not any(t in kept_ids for t in targets):
                continue
            if len(targets) < filters.min_turn_degree:
                continue
            src = graph.sources.get(turn_id)
            if src is None:
                continue
            turn_hubs.append(src)
            for t in targets:
                real = edge_by_pair.get((turn_id, t))
                if real is not None:
                    turn_edges.append(real)
                else:
                    turn_edges.append(Edge(
                        type="support",  # default hyperedge type for citation-only spokes
                        source=turn_id,
                        target=t,
                        established_at=turn_id,
                        voices=[src.speaker] if src.speaker else [],
                        confidence="low",
                    ))
                if t not in kept_ids:
                    hub_partners.add(t)

        # Pull low-mass hub partners back in as ghost concepts so
        # the full hub-and-spoke shape is visible.
        for pid in hub_partners:
            partner = graph.concepts.get(pid)
            if partner is None:
                continue
            if filters.classes is not None and partner.class_ not in filters.classes:
                continue
            kept.append(partner)
            kept_ids.add(pid)

    class_counts: dict[str, int] = {}
    nature_counts: dict[str, int] = {}
    for c in kept:
        class_counts[c.class_] = class_counts.get(c.class_, 0) + 1
        nature_counts[c.nature] = nature_counts.get(c.nature, 0) + 1

    return VizPayload(
        concepts=kept,
        edges=kept_edges,
        depths=depths,
        n_total_concepts=len(graph.concepts),
        n_total_edges=len(graph.edges),
        class_counts=class_counts,
        nature_counts=nature_counts,
        filters=filters,
        turns=turn_hubs,
        turn_edges=turn_edges,
    )


def payload_to_dict(payload: VizPayload) -> dict:
    """JSON-ready dict for HTML templates (D3, Cytoscape, Three.js).

    Shape matches the contract in `VIZ_DESIGN.md`: meta block with
    counts, one entry per concept (includes tree depth), one per
    structural edge. Event edges are already filtered out by
    `build_payload`.
    """
    return {
        "meta": {
            "n_concepts": len(payload.concepts),
            "n_edges": len(payload.edges),
            "n_total_concepts": payload.n_total_concepts,
            "n_total_edges": payload.n_total_edges,
            "class_counts": payload.class_counts,
            "nature_counts": payload.nature_counts,
            "min_mass": payload.filters.min_mass,
        },
        "concepts": [
            {
                "id": c.id,
                "topic": c.topic,
                "class": c.class_,
                "nature": c.nature,
                "state": c.state,
                "mass": round(c.mass, 4),
                "parent": c.parent,
                "voices": list(c.voices),
                "source_refs": list(c.source_refs),
                "first_voiced_at": c.first_voiced_at,
                "last_touched_at": c.last_touched_at,
                "depth": payload.depths.get(c.id, 0),
            }
            for c in payload.concepts
        ],
        "edges": [
            {
                "id": e.id,
                "type": e.type,
                "source": e.source,
                "target": e.target,
                "voices": list(e.voices),
                "confidence": e.confidence,
            }
            for e in payload.edges
        ],
        "turns": [
            {
                "id": t.id,
                "session_id": t.session_id,
                "speaker": t.speaker,
                "turn_idx": t.turn_idx,
                "preview": t.text[:160] if t.text else "",
                "timestamp": t.timestamp,
            }
            for t in payload.turns
        ],
        "turn_edges": [
            {
                "id": e.id,
                "type": e.type,
                "source": e.source,    # turn id
                "target": e.target,    # concept id
                "voices": list(e.voices),
            }
            for e in payload.turn_edges
        ],
    }


def ephemeral_decoration(concept: Concept) -> str:
    """Short decoration appended to an ephemeral concept's label to
    show its state at a glance. Non-ephemerals return empty string."""
    if concept.class_ != "ephemeral" or concept.state is None:
        return ""
    return {
        "open": "",
        "consumed": " ✓",
        "retracted": " ⊥",
        "stale": " ·",
    }.get(concept.state, "")
