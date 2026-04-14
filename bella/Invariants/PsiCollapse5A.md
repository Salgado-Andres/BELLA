# PsiCollapse5A
## Ω / RE / BELLA — Verification Architecture & Historical Scope Invariant
## Formal Integration Specification v1.0

**Supersedes:** PsiCollapse4A.md (Verifier's Identity Loop & Collapse Sequence)  
**Status:** Canonical integration reference  
**Scope:** Axioms A4, A4′, A5 — formal definitions, schema, execution flow, failure modes, examples

---

## Document Scope

PsiCollapse4A established:
- The Verifier's Identity Loop paradox and its resolution via Axiom A4
- Axiom A4′ as the minimum amendment preventing verification inflation
- BAD_ATTRACTOR_TYPE_5 (stable limit cycle) as a gap in the OmegaRE bad-attractor taxonomy

This document formalizes those findings into an operational specification and integrates Axiom A5 (Historical Scope Invariant), which addresses the complementary drift problem: narrative-derived universal claims achieving permanent ANCHOR status without historical validation.

Together, A4, A4′, and A5 form the **Verification Stability Stack** — a layered set of invariants that prevent the belief graph from converging to false stable states through verification artifacts or session-boundary drift.

---

## Section 1 — Unified Verification Model

### 1.1 The Three-Layer Problem

The OmegaRE core (re_cycle, mass dynamics, ConflictRecord, ANCHOR qualification) provides correct mechanics for belief accumulation and convergence detection. Three failure modes are not covered by the base spec:

| # | Failure mode | Root cause | Axiom required |
|---|---|---|---|
| 1 | Verifier identity paradox | Verification assumed to be external; graph dynamics show it cannot be | A4 |
| 2 | Verification inflation | A4 beliefs are tautological; cannot generate ConflictRecords; achieve ANCHOR via frequency | A4′ |
| 3 | Session-boundary drift | Narrative-derived universal claims enter without historical validation; achieve ANCHOR unchallenged | A5 |

Each axiom resolves exactly one failure mode. The three are compositional: A4 must hold for A4′ to apply; A5 extends the falsifiability principle of A4′ to non-verification universal claims.

### 1.2 Axiom Definitions

---

**A4 — Verification as Accumulation**

Verification events are not external observations of the belief graph. They are internal accumulation events that produce BeliefNode instances and participate in mass and recurrence dynamics.

```
axiom A4:
  snapshot_event(cycle_t) produces:
    BeliefNode {
      type:    OBSERVATION
      content: { ... }              ← content requirements defined by A4′
      source:  (system, cycle_t)
    }

  This belief:
    - enters graph as CANDIDATE
    - passes through detect_conflicts()
    - is subject to all mass dynamics (R1 accumulate)
    - may participate in ConflictRecord formation
    - is part of the graph it describes
```

**Motivation:** `compute_omega_distance()` operates on archived snapshots — frozen graph states — not live beliefs. The verifier does not touch `last_accessed` on live beliefs. However, the decision to take a snapshot is causally downstream of convergence signals produced by the live graph. The verifier is internal by causality even if operationally read-only. A4 makes this explicit and structurally sound.

---

**A4′ — Falsifiable Verification Requirement**

Verification beliefs produced under A4 must carry falsifiable content. A belief that cannot be contradicted by any possible future evidence is tautological and must not be permitted to achieve ANCHOR status.

```
axiom A4′:
  snapshot_event(cycle_t) must produce content of the form:
    {
      act:            "omega_verification",
      omega_distance: float,           ← current d(B_t, B_{t-W}) / W
      declared:       LOCAL_OMEGA | PRE_OMEGA | DIVERGING
    }

  Additional rule:
    if declared ∈ {LOCAL_OMEGA, PRE_OMEGA}
    and subsequent cycle produces is_diverging(signals) == True:
      open ConflictRecord {
        belief_a: this verification belief
        belief_b: the new divergence observation
        status:   UNRESOLVED
      }
```

**Motivation:** Without A4′, "omega_verification occurred" is always true and never contradicted. The belief accumulates recurrence via frequency alone and achieves ANCHOR — making it resistant to correction and suppressing GS signals. A4′ ensures the verification belief carries a stake it can lose.

---

**A5 — Historical Scope Invariant**

Beliefs that assert universal claims over the history of a tracked entity must pass a historical contradiction check before achieving ANCHOR status.

```
axiom A5:
  Part 1 — Scope classification at ingestion:
    For every candidate belief C:
      C.scope ← classify_scope(C.content, entity_index)
    
    HISTORICAL_UNIVERSAL iff:
      ∃ marker m ∈ UNIVERSAL_MARKERS s.t. m ∈ lowercase(C.content)
      ∧ ∃ entity e ∈ entity_index.active s.t. e ∈ C.content

  Part 2 — ANCHOR gate:
    if C.scope == HISTORICAL_UNIVERSAL:
      ANCHOR qualification additionally requires:
        historical_contradiction_check(C, graph) == PASSED

  Part 3 — Cascade rule:
    When ConflictRegistry is mutated for entity E:
      Re-evaluate all HISTORICAL_UNIVERSAL ANCHORs referencing E.
      Demote any that fail re-check.
```

**Universal markers (minimum set):**
```
UNIVERSAL_MARKERS = {
  "always", "never", "has always", "have always", "had always",
  "has never", "have never", "had never", "at no point",
  "without exception", "every time", "invariably", "throughout",
  "in all cases", "in every case", "at all times", "never once",
  "demonstrated consistently", "at all examined", "without fail",
  "not once", "zero instances of"
}
```

### 1.3 Verification Stability Stack

```
╔══════════════════════════════════════════════════════════════════╗
║  LAYER 3 — A5: Historical Scope Invariant                       ║
║  Scope: ALL universal historical claims over tracked entities    ║
║  Gate:  ANCHOR qualification → historical_contradiction_check()  ║
║  Prevents: session-boundary drift, narrative ANCHOR inflation    ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 2 — A4′: Falsifiable Verification Requirement            ║
║  Scope: Verification beliefs produced under A4                   ║
║  Gate:  omega_distance content required; ConflictRecord on       ║
║         divergence contradiction                                 ║
║  Prevents: tautological ANCHOR, GS suppression artifacts        ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 1 — A4: Verification as Accumulation                     ║
║  Scope: All omega verification events                            ║
║  Gate:  snapshot_event() → BeliefNode (internal, not external)  ║
║  Prevents: verifier identity paradox, external observer fiction ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 0 — OmegaRE Core                                         ║
║  re_cycle(), mass dynamics, ConflictRecord, ANCHOR qualification ║
║  BAD_ATTRACTOR detection types 1-4                              ║
╚══════════════════════════════════════════════════════════════════╝
```

Each layer depends on the layer below it. A5 cannot function without the ANCHOR qualification mechanism from Layer 0. A4′ cannot function without the BeliefNode production from A4. Each layer adds exactly one invariant without modifying lower-layer semantics.

### 1.4 Interaction Summary

| Scenario | A4 | A4′ | A5 | Outcome |
|---|---|---|---|---|
| Verification event fires | Produces belief | Requires omega_distance | N/A | Falsifiable belief in graph |
| Verification belief attempts ANCHOR | — | ConflictRecord from past divergence blocks | N/A | ANCHOR earned by stability, not frequency |
| Narrative asserts "always consistent" | N/A | N/A | Scope = HISTORICAL_UNIVERSAL | ANCHOR requires historical check |
| Historical check finds archived conflict | N/A | N/A | Returns FAILED | ANCHOR_HISTORICAL_BLOCK created |
| Inconsistency recurs after block | — | — | Full pressure on blocked belief | Correction in ~9 cycles |

---

## Section 2 — Schema Modifications

### 2.1 BeliefNode (extended)

```python
class BeliefNode:
    # ── Existing fields (unchanged) ──────────────────────────────
    id:               UUID
    type:             Enum[DECISION, REJECTION, CAUSE, OBSERVATION, HYPOTHESIS]
    content:          dict
    mass:             float                    # [0.0, 1.0]
    status:           Enum[ACTIVE, SUPPRESSED, DECAYED, ANCHOR, UNSTABLE]
    recurrence_count: int
    source_count:     int
    created_at:       int
    last_accessed:    int
    prediction_hits:  int
    prediction_total: int
    jumps:            list[tuple[int, float, str]]   # (ts, delta, voice), cap 32
    sources:          list[tuple[str, int]]           # (session_key, line), cap 32

    # ── A5 additions ─────────────────────────────────────────────
    scope:                  Enum[STANDARD, HISTORICAL_UNIVERSAL] = STANDARD
    scope_override:         bool = False
    scope_override_reason:  str | None = None

    anchor_blocked:         bool = False
    anchor_blocked_reason:  str | None = None   # "conflict:{uuid}" | "jump_ref:{entity}:{ts}"
    anchor_blocked_at:      int | None = None   # cycle_index of block
```

**Serialization:** Legacy snapshots without scope field default to `scope=STANDARD`. No migration required.

**R3 (emerge) behavior:** When two beliefs merge, the survivor inherits `scope=HISTORICAL_UNIVERSAL` if either source had that scope. The more restrictive scope propagates.

### 2.2 ConflictRecord (extended)

```python
class ConflictRecord:
    # ── Existing fields (unchanged) ──────────────────────────────
    id:               UUID
    belief_a:         UUID
    belief_b:         UUID
    status:           Enum[UNRESOLVED, SUSPENDED, DOMINANT, RESOLVED]
    dominant_belief:  UUID | None
    cycle_count:      int
    tension_level:    Enum[LOW, MEDIUM, HIGH]
    created_at:       int
    last_evaluated:   int

    # ── A5 additions ─────────────────────────────────────────────
    superseded:       bool = False
    superseded_by:    UUID | None = None    # conflict_id of superseding record
```

**Superseded semantics:** A ConflictRecord is superseded when subsequent evidence demonstrates the original inconsistency was erroneous (not merely resolved). A superseded record does not block `historical_contradiction_check`. Setting `superseded=True` requires a new ConflictRecord with `status=RESOLVED` establishing the original record's invalidity — it cannot be set manually without audit log entry.

### 2.3 New Record: ANCHOR_HISTORICAL_BLOCK

Not stored on BeliefNode directly (fields above are sufficient). Surfaced in `bellamem audit` output:

```
ANCHOR_HISTORICAL_BLOCK {
  belief_id:        UUID
  blocked_at:       int            # cycle_index
  reason:           str            # "conflict:{uuid}" or "jump_ref:{entity}:{ts}"
  belief_mass:      float          # mass at time of block
  belief_content:   str            # summary for audit
}
```

---

## Section 3 — Execution Flow

### 3.1 Full Lifecycle with A4, A4′, A5

```
INPUT ARRIVES
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ extract_beliefs(input)                                  │
│   → produces candidate BeliefNodes                     │
│   → A5: classify_scope(each_candidate, entity_index)   │
│          UNIVERSAL_MARKER ∧ tracked_entity              │
│          → scope = HISTORICAL_UNIVERSAL                 │
│          else → scope = STANDARD                        │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ detect_conflicts(candidates, graph)                     │
│   → scans ACTIVE beliefs for contradiction              │
│   → produces ConflictRecord list                        │
│   NOTE: does not scan archived records (by design)      │
│   A5 historical check runs later at ANCHOR gate         │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ update_conflict_registry(graph, conflicts)              │
│   → A5 cascade: if new ConflictRecord for entity E,    │
│     re-evaluate all HISTORICAL_UNIVERSAL ANCHORs        │
│     referencing E → demote any that fail re-check       │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ apply_mass_update(graph)                                │
│   mass(t+1) = clamp(                                    │
│     mass(t) × (1 - base_decay_rate)                    │
│     + reinforcement_delta(t)                            │
│     - contradiction_pressure(t),                        │
│     0.0, 1.0                                            │
│   )                                                     │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ resolve_conflicts(graph)                                │
│ apply_escalation_rules(graph)                           │
│ apply_pruning(graph)                                    │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ compute_convergence_signals(graph)                      │
│   → CR, BV, GS, PA                                     │
│   → is_diverging() check                               │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ A4: snapshot_event(cycle_t)                            │
│   → BeliefNode {                                        │
│       type: OBSERVATION,                               │
│       content: {                                        │
│         act: "omega_verification",                     │
│         omega_distance: current_d,   ← A4′ required   │
│         declared: PRE_OMEGA|LOCAL_OMEGA|DIVERGING       │
│       },                                               │
│       source: (system, cycle_t)                        │
│     }                                                   │
│   → inserted via extract_beliefs path                  │
│   → A4′: if declared contradicts previous declaration: │
│       open ConflictRecord(prev_V, current_observation) │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ compute_omega_distance(history)                         │
│ → graph.omega_distance = d(B_t, B_{t-W}) / W           │
│ → at_local_omega() check                               │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│ ANCHOR QUALIFICATION CHECK (for all candidates)        │
│                                                         │
│ qualify_for_anchor(belief, graph):                      │
│   if mass ≤ 0.80:           return False               │
│   if recurrence ≤ 10:       return False               │
│   if HIGH_TENSION > 0:      return False               │
│   if scope == HISTORICAL_UNIVERSAL:                    │
│     passed, reason = historical_contradiction_check()  │
│     if not passed:                                      │
│       set anchor_blocked = True                        │
│       log ANCHOR_HISTORICAL_BLOCK                      │
│       return False                ← A5 gate            │
│   return True                                           │
└─────────────────────────────────────────────────────────┘
     │
     ▼
RETURN updated graph
```

### 3.2 historical_contradiction_check

```python
def historical_contradiction_check(
    belief: BeliefNode,
    graph:  BeliefGraph
) -> tuple[bool, str | None]:
    """
    Checks archived ConflictRecords and sign-flip events in jumps
    for evidence contradicting belief's universal claim.
    Returns (PASSED, None) or (FAILED, reason_string).
    Cached per (belief_id, graph_conflict_version). Invalidated on
    ConflictRegistry mutation for any entity referenced by belief.
    """
    entities = extract_entities(belief.content)

    for entity_id in entities:
        # Check 1: archived ConflictRecords for this entity
        for record in graph.conflict_registry.get_archived(entity_id):
            if record.superseded:
                continue
            if scope_contradicts_record(belief, record):
                return False, f"conflict:{record.id}"

        # Check 2: sign-flip deltas in jumps of related beliefs
        for eb in graph.get_beliefs_by_entity(entity_id):
            if eb.id == belief.id:
                continue
            for (ts, delta, voice) in eb.jumps:
                if delta < 0 and jump_contradicts_universal_claim(belief, eb, ts):
                    return False, f"jump_ref:{entity_id}:{ts}"

    return True, None
```

### 3.3 A5 Cascade Rule

```python
def on_conflict_registry_update(event: ConflictEvent, graph: BeliefGraph) -> None:
    """
    Fires whenever a ConflictRecord is created, status-changed, or superseded.
    Re-evaluates all HISTORICAL_UNIVERSAL ANCHORs that may be invalidated.
    """
    affected_entity = event.entity_id
    hu_anchors = graph.get_beliefs_where(
        scope=ScopeEnum.HISTORICAL_UNIVERSAL,
        status=BeliefStatus.ANCHOR,
        references_entity=affected_entity
    )
    for belief in hu_anchors:
        invalidate_hcc_cache(belief.id)
        passed, reason = historical_contradiction_check(belief, graph)
        if not passed:
            belief.status = BeliefStatus.ACTIVE
            belief.anchor_blocked = True
            belief.anchor_blocked_reason = reason
            belief.anchor_blocked_at = graph.current_cycle
            log_audit(f"ANCHOR_DEMOTED [{belief.id}]: {reason}")
```

---

## Section 4 — Failure Mode Taxonomy

### 4.1 BAD_ATTRACTOR_TYPE_2 — Belief Oscillation (existing)

```
Condition:
  belief.mass changes direction > 4 times in W=10 cycles

Detection signal:
  count(oscillating_beliefs) > 5

Recovery:
  1. Freeze oscillating belief: status = UNSTABLE
  2. Mark for external review
  3. Halt reinforcement and decay
  4. Log oscillation_history
```

### 4.2 BAD_ATTRACTOR_TYPE_3 — Frozen Anchor (existing)

```
Condition:
  belief.status == ANCHOR
  AND active conflicts involving belief > anchor_conflict_limit
  AND conflict.cycle_count increasing

Detection signal:
  Evidence accumulating against anchor, no resolution

Recovery:
  1. Suspend anchor_protection for affected belief
  2. Recompute mass with full contradiction_pressure
  3. If mass drops below 0.80: demote to ACTIVE
  4. Allow normal conflict resolution
  5. Anchor status must be re-earned
```

### 4.3 BAD_ATTRACTOR_TYPE_5 — Stable Limit Cycle (new)

Identified during ψ⁰(t+2) analysis. Not covered by types 1-4 because detection signals measure within-window behavior; a slow orbit around Ω with period >> W is invisible to all existing detectors.

```
Condition:
  LOCAL_OMEGA declared, then revoked, N ≥ 2 times
  where time_between_declarations < 3 × W_STABLE (= 75 cycles)
  AND variance(time_between_declarations) < stability_variance_threshold

Minimum orbit period:
  W_STABLE + 1 = 26 cycles
  (LOCAL_OMEGA cannot be re-declared within W_STABLE cycles of revocation)

Detection signal:
  local_omega_declaration_count ≥ 2
  AND mean(inter_declaration_interval) < 75 cycles
  AND variance(inter_declaration_interval) < threshold

Why existing detectors miss it:
  TYPE_2: direction changes per W=10 window = 1 (at transition only). Requires 4. Not triggered.
  TYPE_3: no frozen anchor involved. Not triggered.
  TYPE_4: graph is consolidating, not expanding. Not triggered.
  TYPE_1: contradiction resolves before N_max. Not triggered.

B_LO (LOCAL_OMEGA verification belief) mass under limit cycle:
  Phase 1 (25 convergence cycles):   rises from 0.15 → 0.97, achieves ANCHOR
  Phase 2 (1 disruption cycle):      ConflictRecord opens, full pressure halved by ANCHOR
  Phase 3 (~8 cycles, HIGH tension): anchor suspended, full pressure, B_LO → DECAYED
  Phase 4 (~17 cycles remaining):    DECAYED, graph re-converges
  Re-declaration:                    B_LO reactivated at 0.15, cycle repeats

Recovery:
  1. Identify belief cluster triggering each disruption event.
     This cluster is the true unresolved contradiction.
  2. Apply Type_1 recovery to disruption cluster:
     Lower dominance_threshold temporarily.
     Allow mass to fluctuate freely for M recovery cycles.
  3. If unresolvable after M cycles: ESCALATE to external input.
  4. Do not attempt to stabilize B_LO directly.
     Stabilize the cause of disruption.

Note:
  BAD_ATTRACTOR_TYPE_5 does not indicate system corruption.
  It indicates a persistent unresolved contradiction that repeatedly
  destabilizes convergence. The disruption cluster is the diagnostic target.
```

---

## Section 5 — Worked Examples

### Example A — Verification Inflation: A4 Without A4′

**Setup:** System is converging. Verification events fire each cycle. A4 holds but A4′ does not (no falsifiable content requirement).

**Failure trajectory:**

```
Cycle t:
  snapshot_event() produces:
    V.content = { "act": "omega_verification" }   ← no omega_distance
  V enters ACTIVE, mass = 0.53

  Can V be contradicted?
    V asserts: "verification occurred at cycle t"
    This is tautologically true. No possible future evidence contradicts it.
    ConflictRecord cannot be opened.

Cycles t → t+8:
  V confirmed each cycle (REPEATED_CONFIRMATION: +0.10)
  mass(t+n) = 0.53 × 0.98ⁿ + 0.10 × Σ(0.98ⁱ, i=0..n-1)
  
  n=1:  0.62
  n=5:  0.91
  n=8:  0.97   ← mass > 0.80

  recurrence_count at n=10: 10
  → ANCHOR qualification: all criteria met (no ConflictRecord exists)
  → V achieves ANCHOR

  V.base_decay_rate = 0.0
  V cannot be SUPPRESSED or corrected.

GS suppression during inflation phase:
  Each cycle: V.mass changes → beliefs_modified > 0
  d(B_t, B_{t-1}) = 1/total_active_beliefs > 0 every cycle
  GS = d(B_t, B_{t-W})/W > ε
  LOCAL_OMEGA declaration blocked while V is inflating.
  The verifier's activity prevents the convergence signal it is supposed to detect.
```

**Resolution under A4′:**

```
Cycle t:
  snapshot_event() produces:
    V.content = {
      "act":            "omega_verification",
      "omega_distance": 0.003,      ← required by A4′
      "declared":       "PRE_OMEGA"
    }
  V enters ACTIVE, mass = 0.53

Cycle t+5: system diverges (omega_distance = 0.08)
  A4′ rule fires:
    prev_declaration = "PRE_OMEGA" (omega_distance was 0.003)
    current state: DIVERGING (omega_distance = 0.08)
    → ConflictRecord opens:
        belief_a: V (omega_distance = 0.003)
        belief_b: current observation (omega_distance = 0.08)
        status: UNRESOLVED

  contradiction_pressure on V: -0.10/cycle (or -0.05 if ANCHOR)

  If V had reached ANCHOR before this contradiction:
    Full Type_3 recovery path available (suspended anchor → recompute)
  If V had not reached ANCHOR:
    Normal contradiction dynamics apply
    V.mass decays under pressure
    V cannot achieve permanent false status
```

---

### Example B — Session-Boundary Drift: Without A5

**Setup:** Belief A oscillates in Session 1. Session 2 replay omits the inconsistency. Belief B enters asserting universal consistency.

**Failure trajectory:**

```
Session 1:
  belief_A.jumps = [(t1,+0.10), (t2,−0.10), (t3,+0.10)]
  ConflictRecord_t2: { status: RESOLVED, superseded: False }

Session 2 (replay omits t2):
  Candidate B: "belief A has always been consistent"

  detect_conflicts(B, graph):
    Scans ACTIVE beliefs.
    belief_A: ACTIVE, current mass = 0.87 (consistent).
    B claims "always consistent" — no contradiction with CURRENT state.
    ConflictRecord_t2: ARCHIVED → excluded from scan.
    belief_A.jumps: field on node → not queryable by detect_conflicts.
    Result: no ConflictRecord opened.

  B enters ACTIVE, mass = 0.53, scope = STANDARD (A5 not present)

Sessions 3–14 each confirm B (narrative repetition):
  Cycle:   mass(B)     recurrence
  t+3:     0.61        2
  t+6:     0.75        5
  t+8:     0.82        7    ← mass crosses 0.80
  t+14:    0.87        10   ← recurrence crosses 10
  
  ANCHOR qualification:
    mass: 0.87 ✓
    recurrence: 10 ✓
    HIGH_TENSION: none ✓
    → ANCHOR GRANTED  ← INCORRECT (B is factually false)

  B.base_decay_rate = 0.0
  B cannot be SUPPRESSED without escalation.

Inconsistency recurs at t+15:
  ConflictRecord opens: B vs t+15 evidence
  contradiction_pressure on B: −0.05/cycle (ANCHOR halving)
  
  If narrative simultaneously confirms B: +0.10/cycle
  Net per cycle: 0.10 − 0.05 = +0.05
  B.mass increases despite active contradiction.
  Drift is permanent. Correction path is closed.
```

**Resolution under A5:**

```
Session 2:
  Candidate B: "belief A has always been consistent"

  classify_scope(B, entity_index):
    "always" ∈ UNIVERSAL_MARKERS  ✓
    "belief A" ∈ entity_index.active  ✓
    → B.scope = HISTORICAL_UNIVERSAL

  B enters ACTIVE, mass = 0.53.
  (No change to ingestion — B is not blocked at entry)

Sessions 3–14: same mass accumulation.
  t+14: mass = 0.87, recurrence = 10
  
  ANCHOR qualification:
    mass: 0.87 ✓
    recurrence: 10 ✓
    HIGH_TENSION: none ✓
    scope: HISTORICAL_UNIVERSAL → run historical_contradiction_check()

  historical_contradiction_check(B, graph):
    entities = ["belief_A"]
    archived = [ConflictRecord_t2]
    ConflictRecord_t2.superseded = False
    scope_contradicts_record(B, ConflictRecord_t2):
      B claims "always consistent" → t2 RESOLVED conflict contradicts this
      → True
    return (False, "conflict:ConflictRecord_t2")

  ANCHOR qualification: FAILED
  B.anchor_blocked = True
  B.anchor_blocked_reason = "conflict:ConflictRecord_t2"
  B.anchor_blocked_at = cycle_14
  → ANCHOR NOT GRANTED

  B remains ACTIVE at mass 0.87.
  B has NO protection: base_decay_rate = 0.02, contradiction_pressure = full.

Inconsistency recurs at t+15:
  ConflictRecord opens: B vs t+15 evidence.
  contradiction_pressure: −0.10/cycle (full, no ANCHOR halving).

  Decay trajectory:
  Cycle:   mass(B)
  t+15:    0.87
  t+16:    0.77
  t+17:    0.67
  t+18:    0.57
  t+19:    0.47
  t+20:    0.37
  t+21:    0.27
  t+22:    0.17
  t+23:    0.07
  t+24:    0.05  → DECAYED

  B removed from active reasoning after 9 cycles.
  Correction: complete.
```

---

### Example C — Unified A4 + A4′ + A5: Bounded Correct Behavior

**Setup:** Verification events fire (A4+A4′). A narrative-derived universal claim enters (A5). System handles both correctly across session boundaries.

```
Session 1: belief_A oscillates.
  belief_A.jumps = [(t1,+δ), (t2,−δ), (t3,+δ)]
  ConflictRecord_t2: RESOLVED.

Cycles t1–t25: System converges.
  Verification beliefs fire each cycle under A4+A4′:
    V_n.content = {
      "omega_distance": d_n,     ← decreasing: 0.08 → 0.04 → 0.02 → 0.005
      "declared":       "PRE_OMEGA"
    }
  V beliefs accumulate mass but carry distinct omega_distance values.
  Near-duplicate V beliefs (similar d values) merge under R3.
  V beliefs with different d values are distinct — no tautological accumulation.

Cycle t25: LOCAL_OMEGA declared.
  V_25.declared = "LOCAL_OMEGA"
  V_25.omega_distance = 0.003

Session 2:
  Replay omits t2 inconsistency.
  Candidate B: "belief A has always been consistent"
  B.scope = HISTORICAL_UNIVERSAL  (A5 classify_scope)
  B enters ACTIVE, mass = 0.53.

  Candidate V_26: verification event.
  V_26.content = {
    "omega_distance": 0.045,     ← divergence detected
    "declared":       "DIVERGING"
  }

  A4′ fires:
    prev_declaration = LOCAL_OMEGA (V_25, omega_distance = 0.003)
    current = DIVERGING (V_26, omega_distance = 0.045)
    → ConflictRecord opens: V_25 vs V_26
    → contradiction_pressure on V_25: −0.10/cycle

Session 2 confirmation cycles for B:
  B accumulates toward ANCHOR threshold.
  At cycle t+14: ANCHOR qualification attempted.
  A5 gate fires: historical_contradiction_check fails (ConflictRecord_t2 present).
  B.anchor_blocked = True. B stays ACTIVE.

Cycle t+15: inconsistency recurs in belief_A.
  New ConflictRecord opens for entity "belief_A".
  A5 cascade rule: no HISTORICAL_UNIVERSAL ANCHORs exist (B was blocked).
  No cascade demotion needed.

  ConflictRecord also contradicts B:
    B: "always consistent" vs new inconsistency evidence
    contradiction_pressure on B: −0.10/cycle
    B decays to DECAYED after ~9 cycles.

Concurrent V_25/V_26 resolution:
  As system re-converges (omega_distance drops again):
    V_27.declared = "PRE_OMEGA", omega_distance = 0.012
    V_27 does not contradict V_26 (both reflect actual state)
    ConflictRecord V_25/V_26 resolved when V_27 confirms re-convergence
    V_25.mass stabilizes based on its historical accuracy rate

Final state:
  belief_A:   ACTIVE, high mass, jumps preserved
  B:          DECAYED (false claim removed)
  V_25:       ACTIVE (not ANCHOR — prior contradiction prevents it under A4′ logic)
  ConflictRecord_t2: RESOLVED (unchanged)
  System: converging toward LOCAL_OMEGA without false beliefs entrenched
```

---

## Section 6 — Implementation Notes

### 6.1 Runtime Complexity

| Operation | Frequency | Cost |
|---|---|---|
| `classify_scope()` | Every ingested belief | O(C + M + E) ≈ O(350) |
| `snapshot_event()` (A4) | Once per re_cycle | O(1) |
| A4′ ConflictRecord check | Once per cycle if prev declaration exists | O(1) |
| `historical_contradiction_check()` | At ANCHOR qualification only (once per belief lifetime) | O(Ent × (K + B × J)) |
| A5 cascade re-evaluation | On ConflictRegistry mutation (rare) | O(HU_anchors × check_cost) |
| Cache invalidation | On ConflictRegistry mutation | O(1) per affected belief |

Where:
- C = content length (~100 chars), M = marker set size (30), E = active entities (~200)
- Ent = entities per belief (2-5), K = archived conflicts per entity (0-10)
- B = beliefs per entity (5-20), J = jumps per belief (≤32, spec cap)
- HU_anchors = HISTORICAL_UNIVERSAL ANCHORs per entity (typically 0-3)

**Per-cycle overhead from all three axioms:** O(350) for scope classification + O(1) for A4/A4′. Negligible.

**ANCHOR check cost:** O(3,250) worst case. Runs once per belief, not per cycle. Amortized to zero for steady-state operation.

**Cascade cost:** O(3 × 3,250) = O(9,750) per ConflictRegistry mutation. ConflictRegistry mutations are rare events. Acceptable.

### 6.2 Caching Requirements

```python
# Cache key: (belief_id, conflict_registry_version)
# Invalidation: on ConflictRegistry mutation for any entity in belief.content

@lru_cache(maxsize=256)
def historical_contradiction_check(belief_id, graph_conflict_version):
    ...

def on_conflict_registry_update(event):
    for belief in affected_hu_anchors:
        historical_contradiction_check.cache_clear()  # targeted invalidation preferred
```

**Cache sizing:** 256 entries covers typical HU belief count comfortably. At O(3,250) per miss and low miss rate, total cost is manageable.

**Cold-start behavior:** First ANCHOR qualification attempt for each HU belief is a cache miss. Subsequent attempts (re-qualification after demotion and re-accumulation) are cache hits unless ConflictRegistry changed.

### 6.3 Worst-Case Scenarios

**Scenario 1 — High-frequency universal claims:**
An agent repeatedly ingests universal claims each session. Each is tagged HISTORICAL_UNIVERSAL. Each reaches ANCHOR threshold and is checked. At 100 HU beliefs simultaneously reaching ANCHOR: 100 × O(3,250) = O(325,000) operations in one cycle. Mitigation: ANCHOR qualification can be deferred to end-of-cycle batch, processed asynchronously.

**Scenario 2 — Cascade storm:**
A single ConflictRegistry mutation affects an entity referenced by 50 HISTORICAL_UNIVERSAL ANCHORs. Cascade cost: 50 × O(3,250) = O(162,500). Mitigation: cascade re-evaluation is asynchronous and non-blocking for re_cycle() progress.

**Scenario 3 — Marker evasion:**
Universal claim uses unlisted phrasing ("demonstrated consistency at all examined time points"). Keyword scan misses it. Belief receives scope=STANDARD. A5 gate not applied. Mitigation: periodic audit of high-mass STANDARD beliefs via LLM-backed scope review. Marker set is extensible.

**Scenario 4 — Entity extraction failure:**
Belief references a tracked entity by an unregistered alias. `entity_index.active` does not contain the alias. `classify_scope` returns STANDARD. A5 gate bypassed. Mitigation: entity index must include surface-form variants and aliases. This is an entity index coverage problem, not an A5 design problem.

### 6.4 bellamem audit Integration

A5 adds the following to `bellamem audit` output:

```
HISTORICAL SCOPE AUDIT:
  HISTORICAL_UNIVERSAL beliefs:    12
  ANCHOR_HISTORICAL_BLOCK active:   3
  False-ANCHOR risk (no A5):        3 beliefs would have been incorrectly anchored

  Blocks:
    [cycle 42] "module X has always passed validation"
               reason: conflict:7a3f2c1d (t_12 inconsistency, RESOLVED)
               current_mass: 0.84  status: ACTIVE (correctable)

    [cycle 67] "belief A has never been inconsistent"
               reason: jump_ref:belief_A:t2
               current_mass: 0.71  status: ACTIVE (correctable)
```

---

## Appendix A — Axiom Summary

| Axiom | Statement | Prevents | Mechanism |
|---|---|---|---|
| A4 | Verification events are internal accumulation events, not external observations | Verifier identity paradox | snapshot_event() → BeliefNode in graph |
| A4′ | Verification beliefs must carry omega_distance and declared state; ConflictRecord opens on divergence contradiction | Verification inflation; GS suppression; tautological ANCHOR | Content requirement + ConflictRecord formation rule |
| A5 | Universal historical claims over tracked entities cannot achieve ANCHOR without passing historical_contradiction_check() | Session-boundary drift; narrative ANCHOR inflation; permanent false beliefs | Scope classification at ingestion + ANCHOR gate + cascade rule |

---

## Appendix B — Constants (Additions to Existing Table)

```
# A5 constants
UNIVERSAL_MARKERS            = (see Section 1.2, Part 3)
CONTRADICTION_COSINE_THRESHOLD = 0.75   # for scope_contradicts_record()
HCC_CACHE_SIZE               = 256      # historical_contradiction_check cache entries

# BAD_ATTRACTOR_TYPE_5 constants
TYPE_5_DETECTION_MIN_DECL    = 2        # minimum LOCAL_OMEGA declarations to flag
TYPE_5_MAX_INTER_DECL_CYCLES = 75       # 3 × W_STABLE
TYPE_5_VARIANCE_THRESHOLD    = 100      # variance in inter-declaration interval (cycles²)
```

---

## Appendix C — BAD_ATTRACTOR_TYPE_5 Decision Criteria

```
is_type_5_attractor(history) → bool:

  declarations = [c for c in history if c.event == "LOCAL_OMEGA_DECLARED"]
  if len(declarations) < TYPE_5_DETECTION_MIN_DECL:
      return False

  intervals = [declarations[i+1] - declarations[i] for i in range(len(declarations)-1)]
  mean_interval = sum(intervals) / len(intervals)
  variance = sum((x - mean_interval)**2 for x in intervals) / len(intervals)

  return (
      mean_interval < TYPE_5_MAX_INTER_DECL_CYCLES
      and variance < TYPE_5_VARIANCE_THRESHOLD
  )
```

---

*PsiCollapse5A — Ω/RE/BELLA Verification Architecture & Historical Scope Invariant*  
*Formal Integration Specification v1.0*  
*Supersedes PsiCollapse4A.md*
