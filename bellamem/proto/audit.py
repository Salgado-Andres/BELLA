"""Audit layer — entropy and health signals over a v0.2 graph.

This is the v0.2 replacement for the flat v0.1 audit/entropy pass.
All signals are computed from the current graph state — no baseline
comparison, no session diff. For "what changed since last time"
use bellamem.proto.resume's recent-activity section.

Signals:
  - mass_entropy: normalized Shannon entropy of concept.mass
  - concept_density: concepts per source (higher = more explosion)
  - structural_edge_ratio: cc edges / all edges
  - orphan_refs: citations pointing at missing sources
  - ephemeral_health: fractions of open / consumed / retracted / stale
  - mass_floor_fraction: concepts stuck at m≤0.501 (R1 health check)

Each signal comes with a human-readable `verdict` (ok / soft / hard)
so the resume output can highlight red flags without the caller
having to interpret raw numbers.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from bellamem.proto.graph import Graph
from bellamem.proto.viz import STATIC_EDGE_TYPES


# Thresholds are calibrated to the current v0.2 ingest. They're
# explicit here rather than scattered through the reporting code
# so that tightening them as the extractor improves is a one-line
# change per threshold.
_DENSITY_SOFT = 0.60     # >0.6 concepts per source = noticeable explosion
_DENSITY_HARD = 0.85     # >0.85 = runaway
_STRUCTURAL_SOFT = 0.10  # <10% cc-edges = thin structural layer
_STRUCTURAL_HARD = 0.04  # <4% = bipartite transcript, not a concept graph
_FLOOR_SOFT = 0.20       # >20% of concepts at m=0.5 floor = R1 starving
_FLOOR_HARD = 0.50       # >50% = R1 effectively off
# mass_spread is higher-is-better: a healthy graph has concepts
# landing in 3+ distinct mass buckets, reflecting different levels
# of ratification. Everyone-in-one-bucket = 0 = no discrimination.
_SPREAD_SOFT = 0.20
_SPREAD_HARD = 0.08


@dataclass
class Signal:
    name: str
    value: float
    verdict: str           # "ok" | "soft" | "hard"
    note: str              # one-line human explanation


@dataclass
class AuditReport:
    n_concepts: int
    n_edges: int
    n_sources: int
    signals: list[Signal]
    ephemeral: dict[str, int]

    def red_flags(self) -> list[Signal]:
        return [s for s in self.signals if s.verdict in ("soft", "hard")]

    def any_hard(self) -> bool:
        return any(s.verdict == "hard" for s in self.signals)


# ---------------------------------------------------------------------------
# Individual metric functions
# ---------------------------------------------------------------------------

def mass_spread(graph: Graph) -> float:
    """Normalized bucket-entropy of the mass distribution.

    Quantizes each concept's mass into one of 10 buckets over [0.5, 1.0],
    then computes Shannon entropy of the bucket populations normalized
    by log(10). Result is in [0, 1]:
      - 0.0 = all concepts in the same bucket (no discrimination,
              usually everyone at m=0.5 floor OR all at same ratification level)
      - 1.0 = population evenly spread across all 10 mass buckets
              (perfect discrimination — distinct beliefs sit at
              distinctly different masses)
      - healthy graphs with active R1 sit ~0.3–0.6: most concepts
        cluster in a few mid-mass buckets with a long tail up to m≈0.9

    Higher = better (more discrimination). Unlike Shannon entropy on
    raw masses, this is sensitive to *where* concepts sit in the mass
    range — all-at-floor reads as 0.0 even with 600 concepts, where
    raw-mass Shannon entropy would read ~1.0 (misleadingly uniform).
    """
    if not graph.concepts:
        return 0.0
    buckets = [0] * 10
    for c in graph.concepts.values():
        idx = int((c.mass - 0.5) * 20)  # 0.50→0, 0.55→1, …, 1.00→10
        if idx < 0:
            idx = 0
        if idx > 9:
            idx = 9
        buckets[idx] += 1
    total = sum(buckets)
    if total == 0:
        return 0.0
    probs = [b / total for b in buckets if b > 0]
    if len(probs) <= 1:
        return 0.0
    h = -sum(p * math.log(p) for p in probs)
    return h / math.log(10)


def concept_density(graph: Graph) -> float:
    """Concepts per source turn. High values mean the extractor is
    minting a new concept almost every turn rather than ratifying
    existing ones. Empty sources → 0."""
    if not graph.sources:
        return 0.0
    return len(graph.concepts) / len(graph.sources)


def structural_edge_ratio(graph: Graph) -> float:
    """Fraction of edges that are concept→concept structural edges
    (cause/elaborate/dispute/support where both endpoints are
    concepts). A healthy concept graph has this above ~10%; below
    ~5% it's a bipartite transcript with tags, not a concept map."""
    if not graph.edges:
        return 0.0
    structural = 0
    for e in graph.edges.values():
        if e.type not in STATIC_EDGE_TYPES:
            continue
        if e.source not in graph.concepts or e.target not in graph.concepts:
            continue
        structural += 1
    return structural / len(graph.edges)


def mass_floor_fraction(graph: Graph) -> float:
    """Fraction of concepts stuck at m ≤ 0.501. High values mean R1
    is not firing for most of the graph (either ingest never called
    cite() with a speaker, or citations came from one voice only)."""
    if not graph.concepts:
        return 0.0
    at_floor = sum(1 for c in graph.concepts.values() if c.mass <= 0.501)
    return at_floor / len(graph.concepts)


def orphan_refs(graph: Graph) -> int:
    """Count of concept source_refs pointing at nonexistent sources.
    Indicates corrupted citations or partial ingest state."""
    missing = 0
    for c in graph.concepts.values():
        for sr in c.source_refs:
            if sr not in graph.sources:
                missing += 1
    return missing


def ephemeral_health(graph: Graph) -> dict[str, int]:
    """Count of ephemerals by state. A growing `open` count with a
    stagnant `consumed` count indicates the extractor is missing
    completion events."""
    out = {"open": 0, "consumed": 0, "retracted": 0, "stale": 0, "none": 0}
    for c in graph.concepts.values():
        if c.class_ != "ephemeral":
            continue
        key = c.state if c.state in out else "none"
        out[key] += 1
    return out


# ---------------------------------------------------------------------------
# Verdict assembly
# ---------------------------------------------------------------------------

def _verdict(value: float, soft: float, hard: float, higher_is_worse: bool = True) -> str:
    if higher_is_worse:
        if value >= hard: return "hard"
        if value >= soft: return "soft"
        return "ok"
    else:
        if value <= hard: return "hard"
        if value <= soft: return "soft"
        return "ok"


def audit(graph: Graph) -> AuditReport:
    """Compute all signals and assemble an AuditReport."""
    density = concept_density(graph)
    structural = structural_edge_ratio(graph)
    floor = mass_floor_fraction(graph)
    spread = mass_spread(graph)
    orphans = orphan_refs(graph)

    signals: list[Signal] = [
        Signal(
            name="concept_density",
            value=density,
            verdict=_verdict(density, _DENSITY_SOFT, _DENSITY_HARD),
            note=f"{density:.2f} concepts per source "
                 f"({len(graph.concepts)}/{len(graph.sources)}) — "
                 f"high values mean the extractor splits ideas into sub-attributes",
        ),
        Signal(
            name="structural_edge_ratio",
            value=structural,
            verdict=_verdict(structural, _STRUCTURAL_SOFT, _STRUCTURAL_HARD,
                             higher_is_worse=False),
            note=f"{structural:.0%} of edges are concept↔concept — "
                 f"below 10% reads as bipartite transcript, not a concept graph",
        ),
        Signal(
            name="mass_floor_fraction",
            value=floor,
            verdict=_verdict(floor, _FLOOR_SOFT, _FLOOR_HARD),
            note=f"{floor:.0%} of concepts at m=0.5 floor — "
                 f"high values mean R1 never fired "
                 f"(run `bellamem.proto rebuild-mass`)",
        ),
        Signal(
            name="mass_spread",
            value=spread,
            verdict=_verdict(spread, _SPREAD_SOFT, _SPREAD_HARD,
                             higher_is_worse=False),
            note=f"mass-bucket entropy {spread:.2f} — "
                 f"low values mean ratification isn't discriminating "
                 f"(concepts cluster in one or two mass buckets)",
        ),
        Signal(
            name="orphan_refs",
            value=float(orphans),
            verdict="hard" if orphans > 0 else "ok",
            note=f"{orphans} citations point at missing sources "
                 f"— should always be 0",
        ),
    ]

    return AuditReport(
        n_concepts=len(graph.concepts),
        n_edges=len(graph.edges),
        n_sources=len(graph.sources),
        signals=signals,
        ephemeral=ephemeral_health(graph),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def format_audit(report: AuditReport) -> str:
    """Human-readable audit block for inclusion in resume output."""
    lines = [
        f"## audit signals   ({report.n_concepts}c · {report.n_edges}e · {report.n_sources}s)",
    ]
    for s in report.signals:
        mark = {"ok": "  ok", "soft": "SOFT", "hard": "HARD"}[s.verdict]
        lines.append(f"  [{mark}] {s.name:22} {s.note}")
    eh = report.ephemeral
    lines.append(
        f"  ephemerals: "
        f"open={eh['open']} consumed={eh['consumed']} "
        f"retracted={eh['retracted']} stale={eh['stale']}"
    )
    return "\n".join(lines)
