"""Tests for bellamem.proto.viz and viz_html.

The viz layer is pure data transform + HTML templating with no
network dependency, so it can be tested against a synthetic Graph
without mocks. These tests pin the invariants that would silently
break the renderer output:
  - min_mass filter keeps/drops concepts correctly
  - edge-partner expansion pulls in low-mass cc neighbors
  - turn hubs build from concept.source_refs (not graph.edges)
  - hub partners are ghosted in when below the mass floor
  - payload_to_dict shape matches the template contract
  - viz_html.render inlines the payload (no __PAYLOAD__ token left)
"""
from __future__ import annotations

from pathlib import Path

from bellamem.proto import Concept, Edge, Graph, Source
from bellamem.proto.viz import (
    Filters, build_payload, payload_to_dict,
)


def _make_graph() -> Graph:
    """Synthetic graph: 4 concepts + 3 turns. One high-mass concept,
    one mid-mass, two at the 0.5 floor. One cc-edge between a kept
    and a filtered concept. One turn citing 3 concepts (hub-worthy)."""
    g = Graph()

    # Turns (sources)
    for tid in (1, 2, 3):
        g.add_source(Source(
            session_id="s1", file_path="/fake.jsonl",
            speaker="user" if tid % 2 else "assistant",
            turn_idx=tid, text=f"turn {tid} text", timestamp=1000.0 + tid,
        ))

    # Concepts
    hi = Concept(id="hi", topic="high mass thing", class_="invariant",
                 nature="metaphysical", mass=0.72)
    mid = Concept(id="mid", topic="mid mass thing", class_="decision",
                  nature="normative", mass=0.58)
    lo1 = Concept(id="lo1", topic="low mass A", class_="observation",
                  nature="factual", mass=0.5)
    lo2 = Concept(id="lo2", topic="low mass B", class_="ephemeral",
                  nature="factual", mass=0.5)
    for c in (hi, mid, lo1, lo2):
        g.add_concept(c)

    # source_refs — turn 1 cites hi + lo1 + lo2 (hub with 3 spokes),
    # turn 2 cites just mid (not a hub), turn 3 cites hi + mid.
    g.concepts["hi"].source_refs = ["s1#1", "s1#3"]
    g.concepts["mid"].source_refs = ["s1#2", "s1#3"]
    g.concepts["lo1"].source_refs = ["s1#1"]
    g.concepts["lo2"].source_refs = ["s1#1"]

    # cc-edge: cause(hi → lo1). Tests edge-partner expansion since
    # lo1 is below default min_mass.
    g.add_edge(Edge(
        type="cause", source="hi", target="lo1",
        established_at="s1#3", voices=["user"], confidence="medium",
    ))

    g.rebuild_indices()
    return g


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def test_min_mass_keeps_high_mass_drops_floor():
    g = _make_graph()
    # Disable both expansions to see the raw filter result.
    p = build_payload(g, Filters(
        min_mass=0.55, expand_edge_partners=False, include_turn_hubs=False,
    ))
    ids = {c.id for c in p.concepts}
    assert "hi" in ids
    assert "mid" in ids
    assert "lo1" not in ids
    assert "lo2" not in ids


def test_edge_partner_expansion_pulls_in_cc_neighbor():
    g = _make_graph()
    # With edge expansion on, lo1 gets pulled in because hi→lo1 is
    # a cc cause-edge and hi is kept.
    p = build_payload(g, Filters(
        min_mass=0.55, expand_edge_partners=True, include_turn_hubs=False,
    ))
    ids = {c.id for c in p.concepts}
    assert "lo1" in ids
    # The cc edge should now appear in the kept edge set.
    edge_types = {(e.source, e.target, e.type) for e in p.edges}
    assert ("hi", "lo1", "cause") in edge_types


# ---------------------------------------------------------------------------
# Hub construction from source_refs (not graph.edges)
# ---------------------------------------------------------------------------

def test_hub_builds_from_source_refs_not_just_edges():
    """Turn 1 has NO explicit Edge in graph.edges but cites 3
    concepts via concept.source_refs. It must still become a hub —
    this is the bug that was hiding 33% of citations."""
    g = _make_graph()
    p = build_payload(g, Filters(
        min_mass=0.55, min_turn_degree=3, expand_edge_partners=False,
    ))
    hub_ids = {t.id for t in p.turns}
    assert "s1#1" in hub_ids, "turn 1 cites 3 concepts but was not built as a hub"
    # The hub should have spokes to hi, lo1, lo2
    spoke_targets = {e.target for e in p.turn_edges if e.source == "s1#1"}
    assert spoke_targets == {"hi", "lo1", "lo2"}


def test_hub_partners_are_ghosted_in():
    """lo1 and lo2 are below min_mass but must appear as ghost
    concepts because they're partners of a qualifying hub (turn 1).
    Without this, hubs render as incomplete rosettes."""
    g = _make_graph()
    p = build_payload(g, Filters(
        min_mass=0.55, min_turn_degree=3, expand_edge_partners=False,
    ))
    ids = {c.id for c in p.concepts}
    assert "lo1" in ids
    assert "lo2" in ids


def test_min_turn_degree_filters_hubs():
    """Turn 3 cites 2 concepts — should NOT be a hub at deg=3."""
    g = _make_graph()
    p = build_payload(g, Filters(min_mass=0.55, min_turn_degree=3))
    hub_ids = {t.id for t in p.turns}
    assert "s1#3" not in hub_ids
    # But at deg=2, turn 3 qualifies
    p2 = build_payload(g, Filters(min_mass=0.55, min_turn_degree=2))
    hub_ids2 = {t.id for t in p2.turns}
    assert "s1#3" in hub_ids2


def test_no_hubs_disables_hub_construction():
    g = _make_graph()
    p = build_payload(g, Filters(min_mass=0.55, include_turn_hubs=False))
    assert p.turns == []
    assert p.turn_edges == []


# ---------------------------------------------------------------------------
# Payload dict shape
# ---------------------------------------------------------------------------

def test_payload_to_dict_has_all_sections():
    g = _make_graph()
    p = build_payload(g, Filters(min_mass=0.55, min_turn_degree=2))
    d = payload_to_dict(p)
    assert set(d.keys()) == {"meta", "concepts", "edges", "turns", "turn_edges"}
    assert set(d["meta"].keys()) >= {
        "n_concepts", "n_edges", "n_total_concepts", "n_total_edges",
        "class_counts", "nature_counts", "min_mass",
    }
    assert d["meta"]["n_total_concepts"] == 4
    # Each concept has the fields the template reads.
    for c in d["concepts"]:
        assert set(c.keys()) >= {
            "id", "topic", "class", "nature", "state", "mass",
            "parent", "voices", "source_refs", "depth",
        }
    for t in d["turns"]:
        assert set(t.keys()) >= {"id", "session_id", "speaker", "turn_idx", "preview"}
    for e in d["turn_edges"]:
        assert set(e.keys()) >= {"id", "type", "source", "target"}


# ---------------------------------------------------------------------------
# HTML emission
# ---------------------------------------------------------------------------

def test_render_html_inlines_payload_no_token_left(tmp_path: Path):
    from bellamem.proto.viz_html import render as render_html
    g = _make_graph()
    out = tmp_path / "out.html"
    render_html(g, out, renderer="d3", filters=Filters(min_mass=0.55))
    html = out.read_text(encoding="utf-8")
    assert "/*__PAYLOAD__*/" not in html, "payload placeholder was not replaced"
    assert '"concepts":' in html
    assert '"turns":' in html
    assert "d3" in html.lower()


def test_render_html_cytoscape_variant(tmp_path: Path):
    from bellamem.proto.viz_html import render as render_html
    g = _make_graph()
    out = tmp_path / "out.html"
    render_html(g, out, renderer="cytoscape", filters=Filters(min_mass=0.55))
    html = out.read_text(encoding="utf-8")
    assert "cytoscape" in html.lower()
    assert "fcose" in html.lower()
    assert "/*__PAYLOAD__*/" not in html


def test_render_html_unknown_renderer_errors(tmp_path: Path):
    import pytest
    from bellamem.proto.viz_html import render as render_html
    g = _make_graph()
    out = tmp_path / "out.html"
    with pytest.raises(ValueError, match="unknown renderer"):
        render_html(g, out, renderer="threejs", filters=Filters(min_mass=0.55))
