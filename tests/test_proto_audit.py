"""Tests for bellamem.proto.audit — entropy + health signals."""
from __future__ import annotations

from bellamem.proto import Concept, Edge, Graph, Source
from bellamem.proto.audit import (
    audit,
    concept_density,
    ephemeral_health,
    format_audit,
    mass_floor_fraction,
    mass_spread,
    orphan_refs,
    structural_edge_ratio,
)


def _concept(cid: str, *, mass: float = 0.5, class_: str = "observation",
             nature: str = "factual", refs: list[str] | None = None) -> Concept:
    return Concept(
        id=cid, topic=cid, class_=class_, nature=nature,
        mass=mass, source_refs=refs or [],
    )


def _source(sid: str, speaker: str = "user") -> Source:
    session, turn = sid.split("#", 1)
    return Source(
        session_id=session, file_path="/f.jsonl",
        speaker=speaker, turn_idx=int(turn), text="",
    )


# ---------------------------------------------------------------------------
# mass_spread
# ---------------------------------------------------------------------------

def test_mass_spread_empty_graph():
    assert mass_spread(Graph()) == 0.0


def test_mass_spread_all_at_floor_is_zero():
    """Every concept in the same bucket → zero discrimination."""
    g = Graph()
    for i in range(20):
        g.add_concept(_concept(f"c{i}", mass=0.5))
    assert mass_spread(g) == 0.0


def test_mass_spread_rises_with_diversity():
    """Concepts across multiple buckets → nonzero spread."""
    g = Graph()
    # 10 concepts each in 5 different buckets
    for bucket, base_mass in enumerate([0.50, 0.60, 0.70, 0.80, 0.90]):
        for i in range(10):
            g.add_concept(_concept(f"b{bucket}-{i}", mass=base_mass))
    spread = mass_spread(g)
    assert spread > 0.6, f"5 equally-populated buckets should read high, got {spread}"


# ---------------------------------------------------------------------------
# concept_density
# ---------------------------------------------------------------------------

def test_concept_density_high_when_extractor_explodes():
    """One concept per source = density 1.0 (bad)."""
    g = Graph()
    for i in range(10):
        g.add_source(_source(f"s#{i}"))
        g.add_concept(_concept(f"c{i}"))
    assert concept_density(g) == 1.0


def test_concept_density_low_when_concepts_accumulate():
    g = Graph()
    for i in range(20):
        g.add_source(_source(f"s#{i}"))
    for i in range(5):
        g.add_concept(_concept(f"c{i}"))
    assert concept_density(g) == 0.25


# ---------------------------------------------------------------------------
# structural_edge_ratio
# ---------------------------------------------------------------------------

def test_structural_edge_ratio_pure_bipartite_is_zero():
    """All edges are turn→concept — 0 structural."""
    g = Graph()
    g.add_source(_source("s#0"))
    g.add_concept(_concept("a"))
    g.add_edge(Edge(type="support", source="s#0", target="a",
                    established_at="s#0"))
    assert structural_edge_ratio(g) == 0.0


def test_structural_edge_ratio_counts_cc_edges():
    g = Graph()
    g.add_source(_source("s#0"))
    g.add_concept(_concept("a"))
    g.add_concept(_concept("b"))
    g.add_edge(Edge(type="support", source="s#0", target="a",
                    established_at="s#0"))
    g.add_edge(Edge(type="cause", source="a", target="b",
                    established_at="s#0"))
    # 1 of 2 edges is structural
    assert structural_edge_ratio(g) == 0.5


# ---------------------------------------------------------------------------
# mass_floor_fraction
# ---------------------------------------------------------------------------

def test_mass_floor_fraction():
    g = Graph()
    for i in range(10):
        g.add_concept(_concept(f"f{i}", mass=0.5))
    for i in range(5):
        g.add_concept(_concept(f"h{i}", mass=0.75))
    assert mass_floor_fraction(g) == 10 / 15


# ---------------------------------------------------------------------------
# orphan_refs
# ---------------------------------------------------------------------------

def test_orphan_refs_counts_missing():
    g = Graph()
    g.add_source(_source("s#0"))
    g.add_concept(_concept("a", refs=["s#0", "s#99", "s#77"]))  # 2 missing
    assert orphan_refs(g) == 2


def test_orphan_refs_zero_when_all_refs_resolve():
    g = Graph()
    g.add_source(_source("s#0"))
    g.add_source(_source("s#1"))
    g.add_concept(_concept("a", refs=["s#0", "s#1"]))
    assert orphan_refs(g) == 0


# ---------------------------------------------------------------------------
# ephemeral_health
# ---------------------------------------------------------------------------

def test_ephemeral_health_counts_each_state():
    g = Graph()
    g.add_concept(_concept("o1", class_="ephemeral", nature="normative"))  # defaults to open
    g.add_concept(_concept("o2", class_="ephemeral", nature="normative"))
    c3 = _concept("c3", class_="ephemeral", nature="normative")
    c3.state = "consumed"
    g.add_concept(c3)
    c4 = _concept("c4", class_="ephemeral", nature="normative")
    c4.state = "retracted"
    g.add_concept(c4)
    health = ephemeral_health(g)
    assert health["open"] == 2
    assert health["consumed"] == 1
    assert health["retracted"] == 1
    assert health["stale"] == 0


# ---------------------------------------------------------------------------
# audit() integration
# ---------------------------------------------------------------------------

def test_audit_report_flags_bipartite_transcript():
    """A graph with only turn→concept edges should HARD-flag the
    structural_edge_ratio signal — that's the bipartite-transcript
    pathology the metric was designed to catch."""
    g = Graph()
    for i in range(5):
        g.add_source(_source(f"s#{i}"))
        g.add_concept(_concept(f"c{i}", mass=0.5))
        g.add_edge(Edge(type="support", source=f"s#{i}", target=f"c{i}",
                        established_at=f"s#{i}"))
    report = audit(g)
    assert report.any_hard()
    sr = next(s for s in report.signals if s.name == "structural_edge_ratio")
    assert sr.verdict == "hard"


def test_audit_report_healthy_graph_is_ok():
    """A graph with diverse mass, some cc-edges, low density → no hard flags."""
    g = Graph()
    for i in range(50):
        g.add_source(_source(f"s#{i}"))
    # 10 concepts over a wide mass range
    for i, m in enumerate([0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95]):
        g.add_concept(_concept(f"c{i}", mass=m))
    # Mix of cc and bipartite edges — 5 each
    for i in range(5):
        g.add_edge(Edge(type="cause", source=f"c{i}", target=f"c{i+1}",
                        established_at=f"s#{i}"))
        g.add_edge(Edge(type="support", source=f"s#{i}", target=f"c{i}",
                        established_at=f"s#{i}"))
    report = audit(g)
    assert not report.any_hard(), f"healthy graph should not hard-flag, got {[s.name for s in report.red_flags()]}"


def test_format_audit_smoke():
    """format_audit produces a string with all signal names."""
    g = Graph()
    g.add_source(_source("s#0"))
    g.add_concept(_concept("a", mass=0.5, refs=["s#0"]))
    report = audit(g)
    rendered = format_audit(report)
    for name in ("concept_density", "structural_edge_ratio",
                 "mass_floor_fraction", "mass_spread", "orphan_refs"):
        assert name in rendered
