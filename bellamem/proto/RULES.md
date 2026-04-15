# BELLA R1–R6 under the v0.2 schema

Phase 4 of the v0.2 migration: a rule-by-rule mapping from BELLA's
six primitives (R1 accumulate, R2 structure, R3 emerge, R4
self-refer, R5 converge, R6 entangle) to the tree + cross-edges
concept graph. Each section answers: *does the rule still apply,
what does it operate on, and what (if anything) does it need that
v0.2 doesn't yet have?*

This is a design reference, not a spec — nothing here is shipped
code unless the "status" line says so. Keep this file in sync with
the actual implementation as each rule lands.

---

## R1 — Accumulate

**Original (flat graph):** each new evidence event for a belief adds
to its log-odds mass. `belief.accumulate(lr, voice)` is the per-op
hook; ratification (two voices) has higher lr than single-voice
initial ingest.

**v0.2 meaning:** accumulate now applies to *two things*, not one:

1. **Concepts** — each source citation adds to the concept's
   evidence. `Concept.cite(source_id)` appends to `source_refs` and
   updates `last_touched_at`. Mass is not yet Jaynes-weighted in v0.2
   (concepts start at 0.5 and don't update); this is the **first
   deferred item** for R1 — a real accumulate function that bumps
   `mass` based on which voices cited the concept.
2. **Edges** — a first-class generalization. A typed edge (support /
   dispute / cause / voice-cross / retract / consume-success etc.)
   accumulates *voices*. The first voicing creates the edge at
   confidence=medium. Subsequent voicings by different speakers add
   to `edge.voices` and bump `confidence` (medium→high at N≥3).
   Implemented in `Graph.add_edge` — merges on `(type, source,
   target)` identity rather than creating duplicates.

**Status:** edges implemented. Concepts-level accumulate (mass
update on citation) is a TODO — currently mass=0.5 for all concepts
and only changes if the LLM's classification changes.

**What this unlocks:** re-asserting the same decision later in the
session strengthens the edge without duplicating the concept. A
dispute voiced twice (by user and by assistant self-observation)
ratifies the dispute.

---

## R2 — Structure

**Original:** beliefs are structured into `Gene` subtrees rooted at
fields. Parent/child is by `rel` (→ support, ⊥ dispute, ⇒ cause).
Structure is a tree-with-rel-typed edges.

**v0.2 meaning:** structure splits cleanly into two dimensions:

1. **Hierarchical spine** — `Concept.parent` forms a tree. Parent is
   set at creation via the LLM's `parent_hint` field; typically
   populated when a new concept elaborates an existing one
   ("retraction detection" → parent="session narrative parsing").
   Tree queries (`Graph.children_of`) are derivable from this axis
   alone.
2. **Cross-edges** — typed relationships that cut across the tree.
   support / dispute / cause / elaborate / voice-cross / retract /
   consume-*. These are first-class `Edge` objects with their own
   voices/confidence.

**Status:** implemented. The tree spine and the cross-edges coexist
in `Graph` and are queried separately.

**What changes:** in the flat schema, a dispute was a child node
with `rel=⊥`. In v0.2, a dispute is an `Edge` whose `target` is the
disputed concept — the dispute itself doesn't take a node slot
unless the disputing claim is itself a separately-named concept.
This halves the node count for "X is wrong because Y" patterns.

---

## R3 — Emerge

**Original:** beliefs that share enough structure coalesce into
higher-order beliefs. Today's flat implementation runs `emerge()`
over the forest, detecting near-duplicate descriptions by embedding
cosine and merging them under a consolidated belief.

**v0.2 meaning:** emergence operates at two scales:

1. **Concept-level** — near-duplicate concepts (cosine > threshold
   on topic embeddings) merge. This is exactly what
   `Graph.find_similar_concept` already does *at insert time* — if a
   new concept's topic is within DEDUP_COSINE=0.85 of an existing
   concept's topic, the new one becomes a citation of the existing
   one. So basic emergence is already eager, not a separate pass.
2. **Pattern-level** (deferred) — patterns that run through many
   concepts become their own emergent invariants. Example: N
   different ephemerals independently retracted on the same topic
   should emerge as a "rejected class" invariant with nature=
   normative ("do not do X"). This is a **separate pass** that runs
   over tree + cross-edges and proposes new concepts from structural
   patterns — it has no flat-graph analog and is a TODO.

**Status:** concept-level deduplication implemented (at insert
time). Pattern-level emergence is the biggest deferred item — it's
also the most valuable because it's what lets the graph distill
"we've rejected this whole class of approaches" from individual
retractions.

**What this unlocks when pattern-level lands:** the graph produces
its own high-level invariants from recurring structural patterns
without the LLM ever voicing them directly. This is the point of
BELLA in the first place — meaning that arises from evidence
rather than authorial decree.

---

## R4 — Self-refer

**Original:** `__self__` field holds first-person observations about
the agent's own behavior. The guard reads `__self__` to surface
anti-patterns before edits.

**v0.2 meaning:** self-observation becomes a class × nature cell:
`invariant × normative` concepts that describe durable behavioral
preferences of the agent or user. Examples from today's dogfood:
"embedding-then-LLM architecture", "use /bellamem command", "assume
user won't start Claude from subfolder".

**Status:** partially implemented by accident. The LLM classifier
correctly routes "how we should behave" claims into invariant ×
normative without a dedicated `__self__` bucket. The guard reads
them via the generic invariant × normative section. But:

- No explicit *first-person* marker. The flat graph's `__self__`
  distinguished "I tend to reach for try/except" from "we decided to
  use exponential backoff". In v0.2 both land as invariant ×
  normative with no author field.
- **Deferred:** add a `voices` field to `Concept` (analog to the
  edges' voices list) so first-person observations can be filtered
  out from broader normative invariants. Useful for introspection
  queries like "what does the agent know about its own tendencies".

**What this gives us for free:** R4 observations surface through the
existing guard pack alongside other normative invariants, so
anti-pattern signal still reaches the model at edit time.

---

## R5 — Converge

**Original:** beliefs can agree or contradict. When agreement is
strong enough, the graph converges toward a stable state (high-mass
invariants). When contradiction is strong enough, the graph forks
and the competing branches both grow until one wins.

**v0.2 meaning:** convergence is now *mechanical* rather than
algorithmic, because the schema makes it visible directly:

1. **Agreement → mass accumulation on edges.** Multiple `support`
   edges between the same two concepts merge into one edge with
   multiple voices (R1 applied to edges). High-voice support edges
   anchor the pair as a stable relationship.
2. **Contradiction → dispute edges.** The disputed concept stays
   present; the dispute edge marks the relationship. The guard's
   blocking behavior prevents re-introduction of disputed content.
3. **Ephemeral state machine → bounded convergence.** An ephemeral
   plan is either still open (unresolved), consumed (converged on
   the outcome), retracted (converged on rejection), or stale
   (abandoned). This replaces the flat graph's "just keep
   accumulating mass" with an explicit resolution step.

**Status:** implemented via the state machine + edge accumulation.
No separate "converge pass" needed — convergence is a visible
property of the graph at any point in time.

**What's still missing:** no "stale" state transition yet. Ephemeral
plans that never get consumed or retracted just stay open forever.
Need a time-based sweep that flips `state=open → state=stale` for
ephemerals whose `last_touched_at` is older than N days. Small fix,
deferred.

---

## R6 — Entangle

**Original:** beliefs across fields can become entangled — a change
in field A affects beliefs in field B via shared entity references.
The flat implementation tracks `entity_refs` per belief.

**v0.2 meaning:** entanglement becomes a derivable query rather
than a stored property. Concepts share a topic word, a source ref,
or a cross-edge endpoint; the graph's indices (`by_session`,
`children_of`, edge source/target) make these relationships
queryable without per-belief entity tracking.

Example: "what concepts touch the walker primitive?" is a query
that:
1. Starts from concept `walker-primitive`
2. Walks `children_of[walker-primitive]` (tree descendants)
3. Walks all edges where source or target is `walker-primitive`
4. Returns the union

That's entanglement as a graph-walk primitive, not a schema field.

**Status:** partially implemented — the indices exist, the walker
primitive doesn't yet. This is the same "walker primitive" thread
from today's session: `walk(graph, query) → WalkResult` is what R6
needs to become a proper operation rather than ad-hoc per-query
code.

**Deferred:** build the walker primitive when a third walker use
case appears (phase 1 retraction + phase 2 multi-edge + something
else). Until then, entanglement queries are hand-rolled.

---

## Summary of v0.2 rule status

| rule | status | key deferred items |
|---|---|---|
| R1 accumulate | partial (edges done, concepts TODO) | concept mass update on citation |
| R2 structure | done | — |
| R3 emerge | partial (dedup done, pattern-level TODO) | pattern→invariant pass |
| R4 self-refer | partial (implicit via invariant×normative) | first-person voice marker on concepts |
| R5 converge | done (state machine + edge accum) | stale state transition for ephemerals |
| R6 entangle | foundations present, walker TODO | walker primitive + query API |

## What this means for "phase 4 complete"

Phase 4 was "re-validate BELLA R1–R6 under the new schema — do any
rules need to change." Answer: **none of them need to change, but
three of them need incremental implementation work that the flat
graph had and v0.2 currently doesn't.**

The rules are coherent with the v0.2 schema — the question is which
parts are mechanically derived by the schema (R2, R5) vs. which need
additional passes (R3 pattern-level, R6 walker) vs. which need
schema additions (R1 concept mass, R4 voices-on-concepts).

None of the deferred items are blockers for daily use. The hot path
(save/resume/guard/cron) works without them. They're enhancements
that add leverage over time.
