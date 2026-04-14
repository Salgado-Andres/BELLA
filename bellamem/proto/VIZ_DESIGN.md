# v0.2 visualization — design spec

The existing `bellamem/viz/render3d.py` reads the flat schema
(`bella.fields`, `belief.rel`, `belief.jumps`) and produces a
Three.js 3D rendering via UMAP×mass. This doc specifies the v0.2
port — what reads what, what the visual vocabulary is, and how
temporal replay works under the new primitives.

Not code. Reference for a future implementation session.

## Goals

A visualization of `.graph/v02.json` that, at a glance:

1. Shows **class × nature distribution** — which epistemic cells
   the project is building up in.
2. Distinguishes **high-mass** from low-mass concepts — the
   ratified content rises, the one-offs stay small.
3. Shows the **tree spine** (hierarchical decomposition via
   `concept.parent`) as an explicit dimension, not implied.
4. Shows **cross-edges** (support/dispute/cause/elaborate) as
   lateral connections that cut across the tree.
5. Surfaces **ephemeral state** (open/consumed/retracted/stale)
   visually, because state is load-bearing in v0.2.
6. Supports **temporal replay** via `Source.timestamp` — not a
   reconstruction of ingest history, but an honest wall-clock
   view of when each concept and edge came into being.
7. Supports **session filtering** — see just this session, or
   all-time, via `by_session` index.

## Non-goals (explicitly)

- Not a productivity dashboard. No metrics, counts, progress
  bars. Those belong in `bellamem resume` text output.
- Not a debugger. Don't try to show internal state of the
  ingest pipeline. Show the graph, not the engine.
- Not a replacement for `bellamem show` / `stats`. The viz
  complements the CLI, doesn't supplant it.
- Not browser-hosted on a server. Same pattern as the existing
  viz-3d: self-contained HTML with inlined JSON payload, loaded
  from CDN. No build step, no dev loop.

## Data sources — what reads what

| visual element | v0.2 primitive |
|---|---|
| nodes | `graph.concepts.values()` |
| position X/Z | UMAP of `concept.embedding` (2D reduction) |
| position Y (depth) | tree depth from `concept.parent` chain |
| node size | `concept.mass` (scaled — see Size section) |
| node hue | `concept.class_` |
| node outline / saturation | `concept.nature` |
| node texture/animation | `concept.state` (ephemerals only) |
| structural edges | `graph.edges` where type ∈ {support, dispute, cause, elaborate} |
| event edges (replay only) | `graph.edges` where type ∈ {voice-cross, retract, consume-*} |
| timeline | sorted `source.timestamp` across `graph.sources` |
| hover tooltip | `concept.topic`, `concept.mass`, `len(source_refs)` |
| detail panel on click | full concept + sources list + incoming/outgoing edges |

## Layout — UMAP × depth × mass

Three axes, each with a clear meaning:

**X, Z — semantic clustering.** UMAP reduction of concept
embeddings to 2D. Concepts that are semantically near each other
land near each other in the X/Z plane. This is what the current
viz-3d does; keep it.

**Y — tree depth.** Root concepts at the top, leaves at the
bottom. Depth = chain length from `concept.parent` pointers up
to a nodeless root. This makes the tree spine *explicit* rather
than leaving it to force-directed guesswork. Concepts without
parents land at depth 0 (the top plane).

**Size — mass.** `radius = base * (0.5 + concept.mass)`. A
concept at m=0.5 is the reference radius; m=0.95 is 1.9× larger,
m=0.05 is 0.55× smaller. This scales well across the observed
range and keeps all concepts visible even at low mass.

**Pulse — ephemeral state.**
- `open` → gentle breathing pulse (sin-wave scale ±5%)
- `consumed` → solid, no animation, small green halo fade-in
- `retracted` → red border, optional X decal, no animation
- `stale` → desaturated, 40% opacity, no animation

## Color palette — class × nature

Two-dimensional encoding for 12 cells, but readable as two
layers:

**Hue by class** (4 base hues):

| class | hue | meaning |
|---|---|---|
| invariant | **blue** (cool, stable, foundational) | time-invariant principles and facts |
| decision | **orange** (warm, active, committed) | revisable commitments |
| observation | **grey** (neutral, indexical) | factual snapshots |
| ephemeral | **green** (living, in-progress) | lifecycle-bound work |

**Saturation / outline by nature** (3 modifiers):

| nature | modifier | meaning |
|---|---|---|
| factual | pale / desaturated interior | measurable, checkable |
| normative | mid saturation + cool outline | commitments about behavior |
| metaphysical | deep saturation + warm outline | self-model, what the system IS |

So an `invariant × metaphysical` concept is a **deep-blue sphere
with a warm outline** — you see it across the scene. An
`observation × factual` is a **pale grey sphere, no outline** —
it recedes into the background unless you're looking for it.

A 4×3 = 12-cell legend lives in the bottom-right of the HUD, always
visible, showing which cells have any population (grey out the
empty ones to reduce noise).

## Edge vocabulary

Split into two visual layers so the static view doesn't drown.

**Static edges (always rendered):**

| type | style |
|---|---|
| support | thin light grey, 40% opacity, no arrow |
| elaborate | thin green, dashed, directional (parent → child) |
| cause | medium cyan, arrowhead at effect end |
| dispute | medium red, double-line, no arrow |

These are the **concept ↔ concept** relationships. Always visible,
faint enough to not overwhelm the nodes.

**Event edges (replay-only):**

| type | style |
|---|---|
| voice-cross | white flash, very short-lived (~1 virtual sec) |
| retract | red crossing animation, fades target node to "retracted" state |
| consume-success | green sparkle at target, flips target to "consumed" |
| consume-failure | orange flash, flips target to "consumed" with warn halo |

These are **turn → concept** events. Only visible during temporal
replay — they flash when their `established_at` source's
timestamp passes the replay playhead, then disappear. They drive
the state transitions on ephemerals visibly rather than silently.

In static (non-replay) mode, event edges are NOT rendered.
Otherwise the scene becomes unreadable — 100+ voice-cross edges
would occlude everything.

## Temporal replay semantics

The v0.2 graph is a snapshot, but `source.timestamp` makes
time-indexed reconstruction possible without a separate history
store.

**Concept existence at time T:**
```
exists(c, T) = any(source.timestamp ≤ T for source in c.source_refs)
```

**Concept mass at time T:**
```
visible_refs = [s for s in c.source_refs if source.timestamp ≤ T]
replay accumulates mass via R1 using only visible_refs
```

This means mass grows *during replay* the same way it grew during
real ingest — each speaker's first visible ref gives the big
bump, repeats give small bumps. Replay tells the story.

**Edge existence at time T:**
```
exists(e, T) = e.established_at's source.timestamp ≤ T
```

**Ephemeral state at time T:**
```
state_at(c, T):
  first = min(source.timestamp for source in c.source_refs)
  if T < first: return None  # doesn't exist yet
  close_events = [e for e in incoming edges(c) of type consume-* / retract
                  if e.established_at.timestamp <= T]
  if any close_events:
    pick earliest → return "consumed" / "retracted" accordingly
  return "open"
```

**Timeline compression:** idle gaps > 5 minutes collapse to 1
virtual second (Gource-style, same as the current viz-3d). For a
3-day session with only ~10 hours of actual activity, this gives
~10 virtual minutes of replay at normal speed.

**Scrubber UI:** bottom HUD with play/pause, current/total time
label (MM:SS / MM:SS), draggable range slider. Scrubbing to any
point re-derives the full state from the formulas above — no
intermediate storage.

## Session filtering

A checkbox list in the top HUD, one checkbox per session_id
(derived from `graph.by_session`). Unchecking a session hides
all concepts whose sources come *only* from that session. Concepts
with citations from multiple sessions stay visible as long as at
least one citation is from a checked session.

Default: all sessions checked. Most useful toggle: "just this
session" for single-session focus.

## Interaction

- **Mouse drag:** orbit camera around scene origin.
- **Scroll:** zoom in/out.
- **Click node:** open a detail panel on the right side. Shows:
  - topic, class, nature, state, mass
  - first_voiced_at / last_touched_at (wall-clock)
  - voices list
  - source citations (clickable — jumps to that moment in replay)
  - incoming/outgoing edges, grouped by type
- **Hover node:** tooltip with topic + mass.
- **Keyboard:**
  - space = play/pause replay
  - f = filter dialog
  - esc = close detail panel
  - `/` = topic search

## File structure for the v0.2 port

```
bellamem/proto/
  viz.py            # pure data-transform: Graph → payload dict
  viz_template.html # Three.js scene, scrubber, legend, HUD
  __main__.py       # new subcommand: python -m bellamem.proto viz
```

`viz.py` mirrors the structure of `resume.py`: a pure function
that takes a `Graph` and returns a JSON-serializable payload.
`viz_template.html` is self-contained HTML with `{PAYLOAD}`
placeholder. The CLI subcommand inlines the payload and writes
the file.

`viz.build_payload(graph) -> dict` contract:

```python
{
  "meta": {
    "n_concepts": int, "n_edges": int, "n_sources": int,
    "class_counts": {cls: count}, "nature_counts": {nat: count},
    "timeline": {"start": float, "end": float, "compressed_end": float},
    "sessions": [{"id": str, "n_concepts": int}],
  },
  "concepts": [{
    "id": str, "topic": str,
    "class": str, "nature": str, "state": str|None,
    "mass": float, "voices": [str],
    "pos": [x, z],        # UMAP 2D
    "depth": int,         # tree depth → Y
    "parent": str|None,
    "source_refs": [str],
    "first_voiced_at": str,   # source_id
    "last_touched_at": str,
  }],
  "edges": [{
    "type": str, "source": str, "target": str,
    "voices": [str], "established_at": str,
    "confidence": str,
    "is_event": bool,     # True for voice-cross/retract/consume-*
  }],
  "sources": [{
    "id": str, "session_id": str, "speaker": str,
    "turn_idx": int, "timestamp": float|None,
    "preview": str,       # first 200 chars for hover
  }],
  "timeline": [
    {"source_id": str, "timestamp": float, "virtual_timestamp": float,
     "concepts_created": [concept_ids], "concepts_cited": [concept_ids],
     "edges_established": [edge_ids]},
    ...
  ],
}
```

The template reads this payload once at load time and builds the
scene from it. All replay state lives in the template's JS — the
payload is static.

## Implementation phases

**Phase A — minimum viable** (2 commits, no temporal replay):

1. `bellamem/proto/viz.py` with `build_payload(graph)` and
   `render_html(graph, out_path)`. UMAP + Y-depth + class×nature
   coloring + static edges only. No replay. Write HTML file.
2. `bellamem/proto/viz_template.html` — Three.js scene, node
   hover, click detail panel, legend, session filter. No
   scrubber.

Deliverable: `python -m bellamem.proto viz` writes
`.graph/v02.html`, opens in any browser, shows the current graph
as a typed structural snapshot.

**Phase B — temporal replay** (1 commit):

3. Timeline computation in `viz.py` (compressed virtual clock
   from `source.timestamp`).
4. Event-edge rendering in template (voice-cross flashes, state
   transitions on ephemerals).
5. Scrubber UI in template HUD.

Deliverable: scrubber lets you drag through the session's
formation. Ephemeral state transitions animate.

**Phase C — polish** (as needed):

6. Topic search (`/` keyboard).
7. Filter dialog (class/nature/state checkboxes).
8. Export-to-png snapshot button.
9. Live reload via SSE watching `.graph/v02.json` mtime.

## What makes this different from viz-3d's current shape

The current viz-3d (`bellamem/viz/render3d.py`) is
semantically correct for the flat schema — it shows beliefs as
spheres, fields as colored continents, rel as edge types, and
jumps as temporal events. Under v0.2, most of those axes map to
different primitives:

- **fields → class×nature** (4×3=12 cells instead of ad-hoc colors)
- **beliefs → concepts** (topic-keyed, with real mass dynamics)
- **belief.rel → graph.edges** (first-class, 8 types)
- **belief.jumps → source.timestamp + derived state** (no separate event store)

The biggest visual *addition* is the ephemeral state machine —
flat schema had no notion of "plan state," so viz-3d has no
visual vocabulary for it. Under v0.2, state is a load-bearing
axis and needs explicit treatment.

The biggest *simplification* is the edge split into static and
event layers. Flat schema drew all edges statically which worked
at ~1500 beliefs because ratio edges were sparse. Under v0.2,
voice-cross edges scale linearly with ingest (one per cited
turn) — drawing them all statically would hit 500+ edges on a
day's worth of work, drowning the scene. Moving ratification
edges to event-only rendering solves the density problem
structurally.

## Open design questions (to resolve before implementation)

1. **UMAP recomputation cadence.** If the graph grows between
   renders, does UMAP regenerate from scratch (positions drift)
   or keep the old layout (new concepts appear near their UMAP
   nearest neighbor but the rest is stable)? The former is
   simpler; the latter is more legible over time. Incremental
   UMAP is a known problem, not a pre-solved one.

2. **Mass display range.** R1 saturates mass asymptotically at
   1.0. If the visualization uses radius = base × (0.5 + mass),
   a concept at m=0.99 is only 1.5× the size of m=0.5, and a
   concept at m=0.5 is only 1.8× m=0.05. This compresses the
   interesting range. Alternative: use log-odds directly as the
   radius input, which spreads the visual space more evenly
   across the evidence range. TBD after seeing real data.

3. **Topic labels.** At what zoom level do topic labels render?
   Labels on every node is too busy; labels on none is useless.
   Mass-threshold gating (only label concepts with m > 0.7 or
   with 3+ source_refs) is the obvious answer but needs
   calibration against the actual graph.

4. **Cross-session concepts.** A concept cited by multiple
   sessions — does it visually belong to one? None? Hmm.
   Maybe display its primary session (mode of source's session_id)
   with a secondary-session indicator.

5. **Retracted concept visibility in replay.** When the replay
   playhead passes a retract event, the target should visibly
   flip to retracted state. But what if the playhead scrubs
   *back* behind the retract? The state has to un-flip to open.
   Cheap because it's recomputed per-frame from the formulas
   above, but means nothing is cached.

## 2D version — static SVG via graphviz

A companion to the Three.js 3D viz, optimized for **readability
over exploration**. The 3D viz is for looking at the graph as a
living system; the 2D viz is for pasting into documentation,
READMEs, PR descriptions, and printed artifacts.

### Why a 2D viz is distinct, not redundant

The 3D viz has strengths the 2D can't match: camera exploration,
temporal replay, rich animation, interaction. But 3D has real
weaknesses for static inspection:

- **Occlusion.** Dense areas hide nodes behind other nodes.
- **Camera state.** Every reader arrives at a different angle.
- **Not printable.** Screenshots lose the camera state, labels
  shrink, the whole thing looks cluttered at A4.
- **No permanent labels.** 3D hover-tooltips disappear when the
  file is saved.
- **Heavy dependencies.** Three.js + CDN load + WebGL for someone
  who just wants to see the structure is overkill.
- **No text searchability.** A reader can't Ctrl-F for a topic
  inside a rendered 3D HTML.

The 2D viz solves all of these at the cost of losing interactivity
and temporal replay. That tradeoff is correct for a different
audience: readers, not operators.

### Technology — graphviz DOT → SVG

Graphviz is already declared as the `[viz]` optional-dependencies
extra for the legacy 2D graphviz path. Reuse it. Produce a DOT
graph, shell out to `dot`/`fdp`/`neato` via the `graphviz` Python
bindings, get SVG back.

No new dependencies. No build step. Output file is a single
`.svg` — embeddable anywhere markdown is rendered (GitHub,
mkdocs, static sites), scalable to any DPI, KB not MB, and every
topic label is selectable text.

### Layout strategy — clusters by class × nature

The 2D case needs explicit grouping where 3D got grouping for
free via color in a continuous space. Graphviz `cluster_*`
subgraphs are perfect:

```
digraph bella_v02 {
    rankdir = TB;
    splines = curved;
    overlap = false;

    subgraph cluster_invariant_metaphysical {
        label = "invariant × metaphysical";
        style = filled;
        fillcolor = "#e7efff";  // pale blue background
        color = "#4c9aff";       // saturated blue border
        node [shape = circle, style = filled];
        c_walker [label = "walker\nprimitive\nm=0.72", fillcolor = "#4c9aff"];
        ...
    }
    subgraph cluster_invariant_normative { ... }
    subgraph cluster_decision_normative { ... }
    ...

    // Cross-edges between clusters
    c_walker -> c_trichotomy [color = "#51cf66", style = dashed];  // elaborate
    c_anchor -> c_walker [color = "#ff6b6b", style = bold];         // dispute
}
```

12 cluster boxes, one per class × nature cell. Within each
cluster, nodes stack by mass (graphviz `rank=same` groups +
invisible edges enforce ordering when needed). Cross-edges
draw between clusters as curved paths with the type's color
and style.

Empty cells are omitted from the output (don't render an empty
cluster box), so a sparse graph shows only populated cells.

### Visual vocabulary — consistent with 3D

Same palette as the 3D version for visual coherence across
formats:

| element | encoding |
|---|---|
| node hue | class (blue / orange / grey / green) |
| node fill saturation | nature (metaphysical = deep, normative = mid, factual = pale) |
| node border | nature modifier (metaphysical = warm outline, normative = cool outline, factual = none) |
| node size | mass (pt-size scales as `12 + 8*mass`) |
| node label | concept topic, wrapped to ~20 chars |
| node shape | always circle |
| ephemeral `open` | normal |
| ephemeral `consumed` | small green "✓" decoration in label |
| ephemeral `retracted` | dashed border, "⊥" decoration |
| ephemeral `stale` | grey fill, 50% opacity via RGBA |

Edge types map to graphviz attributes:

| edge type | graphviz style |
|---|---|
| support | `color="#aaaaaa" penwidth=0.5` — thin grey |
| elaborate | `color="#51cf66" style=dashed` — green dashed |
| cause | `color="#22b8cf" arrowhead=normal` — cyan arrow |
| dispute | `color="#ff6b6b" penwidth=2 style=bold` — bold red |
| voice-cross | **excluded** — too many, not structurally informative |
| retract | **excluded from static view** — flipped into node decoration |
| consume-success / -failure | **excluded** — flipped into node decoration |

The 2D version drops all event edges and transcodes retraction /
consumption into **node state decorations**. That's a legitimate
simplification: 2D viewers can't replay events, so event edges
have no meaning. What the reader sees is a **snapshot of the
graph's current structural state** with state annotations, not
an animation of how it got there.

### Filtering — mass threshold by default

A full-graph SVG with 500+ concepts will be unreadable regardless
of how pretty the layout is. Default filters keep the output
skimmable:

- `--min-mass` — default 0.55 (drops most single-voice concepts
  at the uniform 0.5 floor; keeps R1-boosted ones). Tunable up
  for smaller sketches or down for full dumps.
- `--class` — filter to a subset of classes (default: all).
- `--state` — filter to a subset of ephemeral states (default:
  include open + consumed; exclude retracted + stale for a
  "what's alive" view).
- `--session` — filter to one session's concepts (uses
  `by_session` index).

These apply before layout so graphviz doesn't waste CPU on
culled nodes.

### CLI surface

Single subcommand, output format by extension:

```bash
python -m bellamem.proto viz                     # default: .graph/v02.html (3D, Three.js)
python -m bellamem.proto viz --out graph.svg     # 2D, graphviz SVG
python -m bellamem.proto viz --out graph.dot     # 2D, raw DOT text (no graphviz call)
python -m bellamem.proto viz --out graph.png     # 2D, graphviz → PNG
python -m bellamem.proto viz --out graph.html    # 3D, Three.js (explicit)

# With filters:
python -m bellamem.proto viz --out invariants.svg --class invariant --min-mass 0.6
python -m bellamem.proto viz --out today.svg --session 853e838e
```

Extension drives the dispatch; filters apply to all formats.
Default output (no `--out`) writes the 3D HTML to
`.graph/v02.html` — the same default destination the legacy
viz-3d used for flat-graph rendering.

### File structure update

```
bellamem/proto/
  viz.py            # shared data transform: Graph → payload
  viz_3d.py         # Three.js-specific rendering (Phase A–C)
  viz_2d.py         # graphviz-specific rendering (2D section)
  viz_template.html # Three.js template (loaded by viz_3d)
  __main__.py       # dispatches viz subcommand by --out extension
```

`viz.py` does the shared filtering + class/nature/state
computation. `viz_3d.py` and `viz_2d.py` read that filtered
payload and produce their respective outputs. This keeps the
filter logic (mass threshold, session, class) in one place
rather than duplicating it per-format.

### 2D-specific implementation phases

**Phase 2D-A — static snapshot** (1 commit):

1. `viz_2d.py` with `render_svg(graph, out_path, min_mass=0.55, ...)`.
2. Builds DOT text with class×nature clusters.
3. Shells out to graphviz `dot` for layout.
4. Writes SVG to output path.
5. Returns the list of concepts/edges included so the caller
   can log `n concepts + n edges rendered, out of N total`.

Deliverable: `python -m bellamem.proto viz --out graph.svg`
produces a readable static diagram of the filtered graph.

**Phase 2D-B — polish** (1 commit):

6. HTML wrapper option: `--out graph.html --format 2d` produces
   the SVG embedded in a minimal HTML page with a JS search
   box (`Ctrl-F` on steroids — filters the SVG nodes by topic
   substring).
7. PNG output via graphviz (useful for slide decks).
8. `--focus CONCEPT_ID` mode: renders the focused concept plus
   its one-hop neighborhood only. Very compact output, good
   for PR descriptions.

### Trade-offs to accept for the 2D viz

- **No temporal replay.** Static view. If you want to see how
  the graph formed, use the 3D version with the scrubber.
- **No interactivity beyond hover-text in SVG.** No click-to-
  expand detail panel. Use 3D for that.
- **Cluster layout gets crowded past ~150 visible concepts.**
  Raise `--min-mass` or filter by class to stay readable. The
  default 0.55 threshold keeps most graphs under that limit.
- **Cross-edges between distant clusters can cross.** Graphviz
  does its best but there's no planarity guarantee for the
  full 12-cluster layout. Acceptable — edges are colored and
  styled so overlap doesn't prevent reading individual ones.
- **Doesn't show voice-cross edges.** Deliberate. They exist
  structurally but don't add information to a static view —
  they'd obscure the structural edges that do.

### Open questions specific to 2D

1. **Within-cluster ordering.** Inside each class×nature box,
   how are concepts arranged? Options: alphabetical by topic,
   by mass descending, by first_voiced_at timestamp. Mass
   descending is probably right (highest-mass first = most
   scannable) but alphabetical is better for searchability.
2. **Edge routing across clusters.** Do dispute edges between
   very distant clusters get drawn at all, or does the viz
   elide them to keep the diagram clean and report them in a
   side table? Edge elision with a summary list is honest
   about "what didn't fit" without letting the layout degrade.
3. **Maximum concept count per rendering.** At some node count
   (probably 200+) the output becomes unreadable regardless.
   Hard-cap via filter auto-tightening? Or render anyway and
   let the user see the density?
4. **How does the 2D viz handle the tree spine?** Graphviz
   `dot` layout respects parent edges as rank constraints.
   Parent concepts end up above children, which is correct.
   But does the cluster grouping fight with the rank layout?
   Need to test — might need `rank=same` hints inside clusters.

## Prerequisites — already satisfied

- ✅ R1 concept mass — mass dynamics are live (3a43816)
- ✅ Source.timestamp — wall-clock is available (e91869c)
- ✅ R5 stale-state — ephemeral states include stale (62c5481)
- ✅ viz-3d merged to master — same lane (ce729eb)
- ✅ class × nature classification stable — tested end-to-end
- ✅ Edge types enumerated and persistent in graph.edges

Nothing remains on the dependency list. When implementation
starts, it can begin at Phase A directly.
