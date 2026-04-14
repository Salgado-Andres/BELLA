"""v0.2-native resume: render the graph as a typed, structured
summary for context reconstitution.

This is the replacement for flat memory-file handoff. Memory notes
can only carry narrative prose — they lose the class × nature
distinction, the state machine, and the edge structure. Resume over
a v0.2 graph preserves all three by rendering separate sections per
epistemic role, so next session can scan structure first and read
prose only where it matters.

Usage:
    from bellamem.proto import load_graph, resume_text
    print(resume_text(load_graph()))

Or from CLI:
    python -m bellamem.proto resume
"""
from __future__ import annotations

import sys
from pathlib import Path

from bellamem.proto.graph import Graph
from bellamem.proto.store import load_graph


def _by_mass(concepts):
    """Sort by mass descending, tie-break by source_ref count so
    concepts at the uniform initial mass (0.5) still order sanely."""
    return sorted(
        concepts,
        key=lambda c: (-c.mass, -len(c.source_refs)),
    )


def _by_source_ref_count(concepts):
    return sorted(concepts, key=lambda c: -len(c.source_refs))


def _by_last_touched(concepts):
    return sorted(
        concepts,
        key=lambda c: c.last_touched_at or "",
        reverse=True,
    )


def resume_text(
    graph: Graph,
    *,
    top_invariant_meta: int = 12,
    top_invariant_norm: int = 10,
    top_invariant_fact: int = 6,
    top_open_ephemeral: int = 15,
    top_retracted: int = 10,
    top_decision: int = 12,
    top_dispute_edges: int = 10,
    top_retract_edges: int = 8,
) -> str:
    """Render a structured summary of the graph.

    Sections are ordered by epistemic priority for context
    reconstitution:

      1. invariant × metaphysical — what the system IS
      2. invariant × normative   — what we commit to
      3. invariant × factual     — structural facts
      4. open ephemerals         — work in progress
      5. retracted ephemerals    — rejected/superseded approaches
      6. recent decisions        — committed choices
      7. dispute edges           — live contradictions
      8. retract edges           — speaker-level retractions
      9. stats footer
    """
    out: list[str] = []

    stats = {
        "concepts": len(graph.concepts),
        "edges": len(graph.edges),
        "sources": len(graph.sources),
    }
    out.append(f"# v0.2 graph resume")
    out.append(
        f"  {stats['concepts']} concepts · "
        f"{stats['edges']} edges · "
        f"{stats['sources']} sources"
    )
    out.append("")

    # 1. Invariant × metaphysical — what the system IS
    invar_meta = _by_mass([
        c for c in graph.concepts.values()
        if c.class_ == "invariant" and c.nature == "metaphysical"
    ])
    out.append(f"## what the system IS — invariant × metaphysical ({len(invar_meta)})")
    for c in invar_meta[:top_invariant_meta]:
        out.append(f"  m={c.mass:.2f} [{len(c.source_refs):2}r] {c.topic}")
    out.append("")

    # 2. Invariant × normative — what we commit to
    invar_norm = _by_mass([
        c for c in graph.concepts.values()
        if c.class_ == "invariant" and c.nature == "normative"
    ])
    out.append(f"## what we commit to — invariant × normative ({len(invar_norm)})")
    for c in invar_norm[:top_invariant_norm]:
        out.append(f"  m={c.mass:.2f} [{len(c.source_refs):2}r] {c.topic}")
    out.append("")

    # 3. Invariant × factual — structural facts
    invar_fact = _by_mass([
        c for c in graph.concepts.values()
        if c.class_ == "invariant" and c.nature == "factual"
    ])
    out.append(f"## structural facts — invariant × factual ({len(invar_fact)})")
    for c in invar_fact[:top_invariant_fact]:
        out.append(f"  m={c.mass:.2f} [{len(c.source_refs):2}r] {c.topic}")
    out.append("")

    # 4. Open ephemerals — work in progress
    open_eph = _by_last_touched([
        c for c in graph.concepts.values()
        if c.class_ == "ephemeral" and c.state == "open"
    ])
    out.append(f"## open work — ephemeral × open ({len(open_eph)})")
    for c in open_eph[:top_open_ephemeral]:
        out.append(f"  [open] {c.topic}")
    out.append("")

    # 5. Retracted ephemerals — rejected/superseded approaches
    retracted = _by_last_touched([
        c for c in graph.concepts.values()
        if c.class_ == "ephemeral" and c.state == "retracted"
    ])
    out.append(f"## retracted approaches — ephemeral × retracted ({len(retracted)})")
    for c in retracted[:top_retracted]:
        out.append(f"  [retracted] {c.topic}")
    out.append("")

    # 6. Recent decisions
    decisions = _by_last_touched([
        c for c in graph.concepts.values()
        if c.class_ == "decision"
    ])
    out.append(f"## recent decisions ({len(decisions)})")
    for c in decisions[:top_decision]:
        out.append(f"  [decision/{c.nature}] {c.topic}")
    out.append("")

    # 7. Dispute edges — live contradictions
    dispute_edges = [e for e in graph.edges.values() if e.type == "dispute"]
    if dispute_edges:
        out.append(f"## disputes — ⊥ edges ({len(dispute_edges)})")
        for e in dispute_edges[:top_dispute_edges]:
            src = graph.concepts.get(e.source)
            tgt = graph.concepts.get(e.target)
            if src and tgt:
                out.append(f"  {src.topic}  ⊥  {tgt.topic}")
            else:
                # source may be a turn id, not a concept id
                tgt_t = tgt.topic if tgt else e.target
                out.append(f"  (turn {e.source})  ⊥  {tgt_t}")
        out.append("")

    # 8. Retract edges — speaker-level retractions
    retract_edges = [e for e in graph.edges.values() if e.type == "retract"]
    if retract_edges:
        out.append(f"## speaker retractions — retract edges ({len(retract_edges)})")
        for e in retract_edges[:top_retract_edges]:
            tgt = graph.concepts.get(e.target)
            tgt_t = tgt.topic if tgt else e.target
            out.append(f"  (turn {e.source})  retract  {tgt_t}")
        out.append("")

    # 9. Stats footer
    by_class = {k: len(v) for k, v in graph.by_class.items()}
    by_nature = {k: len(v) for k, v in graph.by_nature.items()}
    ephemeral_states = {}
    for c in graph.concepts.values():
        if c.class_ == "ephemeral":
            s = c.state or "?"
            ephemeral_states[s] = ephemeral_states.get(s, 0) + 1
    edge_types = {}
    for e in graph.edges.values():
        edge_types[e.type] = edge_types.get(e.type, 0) + 1

    out.append("## stats")
    out.append(f"  by_class:  {by_class}")
    out.append(f"  by_nature: {by_nature}")
    out.append(f"  ephemeral_states: {ephemeral_states}")
    out.append(f"  edge_types: {edge_types}")

    # 10. Audit signals — only surface red flags (soft/hard); ok signals
    # are the common case and would drown the useful ones. `bellamem
    # audit` shows the full report.
    from bellamem.proto.audit import audit as _audit
    report = _audit(graph)
    flags = report.red_flags()
    if flags:
        out.append("")
        out.append("## audit — red flags")
        for s in flags:
            mark = {"soft": "SOFT", "hard": "HARD"}[s.verdict]
            out.append(f"  [{mark}] {s.name}: {s.note}")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """CLI: `python -m bellamem.proto resume [--graph PATH]`"""
    import argparse
    ap = argparse.ArgumentParser(prog="bellamem.proto resume")
    ap.add_argument(
        "--graph",
        type=Path,
        default=None,
        help="path to v0.2 graph JSON (default: .graph/v02.json)",
    )
    args = ap.parse_args(argv)

    graph = load_graph(args.graph)
    if not graph.concepts:
        print(
            f"warning: graph is empty "
            f"({args.graph or '.graph/v02.json'} not found or has no concepts)",
            file=sys.stderr,
        )
        return 1

    print(resume_text(graph))
    return 0


if __name__ == "__main__":
    sys.exit(main())
