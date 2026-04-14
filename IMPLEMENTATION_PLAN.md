# BELLA Integration Plan — PsiCollapse5A + SIMTraversal

## Scope and approach
This plan integrates `bella/Invariants/PsiCollapse5A.md` first, then `bella/Transversal/SIMTraversal.md`, as a minimal extension of existing BELLA (`bellamem`) internals. The repo currently has no native `ConflictRecord`/`ANCHOR` lifecycle object model; those are introduced in a small additive core module and wired into existing lifecycle touchpoints without redesigning routing, Jaynes accumulation, replay, or R3 emerge.

## Phase 1 — Repo analysis (where specs attach)

### Existing BELLA structures mapped to spec terms
- **BeliefNode equivalent:** `bellamem/core/gene.py::Belief` (mass, voices, jumps, sources, entity_refs, rel, parent/children).  
- **ConflictRecord equivalent:** no concrete type exists today (only dispute edges via `REL_COUNTER` beliefs); conflict lifecycle must be added.  
- **Anchor qualification logic:** no explicit anchor status/gate exists today (mass + voices exist, but no ANCHOR state machine); must be added as optional additive logic.  
- **Verification/observation event logic:** ingestion pipeline and claim routing in `bellamem/core/bella.py` (`Claim`, `Bella.ingest`) are the right insertion points for A4/A4′ observation beliefs.  
- **Replay/audit/convergence logic:**
  - replay: `bellamem/core/replay.py`
  - audit rendering: `bellamem/core/audit.py`
  - convergence-ish structural healing exists in `bellamem/core/emerge.py` (R3 merge), but no omega/conflict convergence mechanics; new instrumentation should surface through audit-compatible report output.

### Relevant files
- `bellamem/core/gene.py` (Belief schema serialization)
- `bellamem/core/bella.py` (ingest lifecycle, claim routing, entity index)
- `bellamem/core/store.py` (snapshot persistence)
- `bellamem/core/ops.py` (merge semantics — scope propagation touchpoint)
- `bellamem/core/audit.py` (new audit section for traversal instrumentation)
- `bellamem/core/__init__.py` (exports)
- `tests/*` (new invariant tests)
- `bella/Invariants/PsiCollapse5A.md` (spec source)
- `bella/Transversal/SIMTraversal.md` (spec source)

## Proposed changes

### Phase 2 (PsiCollapse5A)
1. Add lightweight invariant model module (`bellamem/core/invariants.py`):
   - `ConflictRecord` dataclass (+ A5 fields `superseded`, `superseded_by`; source support for SIMTraversal).
   - Historical scope constants and classifier (`STANDARD` / `HISTORICAL_UNIVERSAL`).
   - Verification event builder for A4/A4′ (`omega_distance`, `declared` required).
   - Anchor gate function with historical contradiction check.
   - Conflict registry mutation hook that cascades historical anchor re-check.
2. Extend `Belief` minimally for A5 and anchor lifecycle:
   - `scope`, `scope_override`, `scope_override_reason`
   - `anchor_blocked`, `anchor_blocked_reason`, `anchor_blocked_at`
   - `is_anchor`, `anchor_cycle`, `source_kind`, `content`, `recurrence_count`
3. Integrate into ingest (`Bella.ingest`):
   - run scope classification after belief creation.
4. Add `Bella` registry state:
   - `conflicts`, `conflict_version`, `traversals`, and minimal counters needed by traversal instrumentation.
5. Persist new fields in snapshots (`store.py`) in backward-compatible optional keys.
6. Tests for A4/A4′/A5 invariants:
   - verification requires falsifiable payload and can conflict later;
   - verification belief cannot anchor when contradicted;
   - historical universal claim blocked from anchor by archived conflict;
   - conflict-registry mutation re-check demotes prior anchor.

### Phase 3 (SIMTraversal)
1. Add `TraversalRecord` dataclass + storage.
2. Quarantine logic:
   - traversal conflicts excluded from anchor/tension checks while `source=TRAVERSAL` and not promoted.
3. Promotion/demotion helpers:
   - pair hash over sorted belief IDs;
   - promotion requires recurrence + distinct voice pairs; capped promotions per cycle (K=2);
   - demotion supersedes promoted organic conflict and creates new traversal conflict.
4. Promotion triggers A5 cascade re-check and mid-cycle anchor requalification block marker.
5. Instrumentation functions:
   - conflict pair resolution rate
   - closure rate
   - convergence delta
   - anchor emergence rates
   - guard block attribution
6. Expose instrumentation in `audit` output section.
7. Tests for quarantine, promotion, demotion, and promotion-triggered historical re-check.

## Unresolved ambiguities / architecture conflicts
1. **Core mismatch:** specs assume existing OmegaRE conflict + ANCHOR machinery, but current BELLA code has none.  
   - Resolution: add additive minimal lifecycle APIs instead of rewriting core behavior.
2. **“Archived contradiction” definition:** current code has no archive partition; conflict status must stand in.  
   - Resolution: treat any unsuperseded conflict record (including resolved) tied to same entities as historical contradiction evidence.
3. **Convergence/omega integration:** no existing omega metric in runtime.  
   - Resolution: implement A4′ verification payload enforcement and contradiction opening behavior without introducing a full omega engine.
4. **Guard linkage:** existing `guard.py` has no conflict-source attribution pipe.  
   - Resolution: instrumentation stores guard events via explicit API; audit reports what is recorded.
5. **Thresholds:** specs define defaults (N/M/P/K/B).  
   - Resolution: implement spec defaults in constants; keep configurable args in helper functions.

## Implementation order
1. Add `IMPLEMENTATION_PLAN.md` (this file).
2. Implement core schema additions + persistence + invariants module (PsiCollapse5A base).
3. Add PsiCollapse5A tests and pass.
4. Implement traversal schema, quarantine/promotion/demotion + instrumentation.
5. Add SIMTraversal tests and audit surface.
6. Add `INTEGRATION_NOTES.md`.
7. Run full test suite.

## Traceability table

| Spec requirement | Target file(s) | Test proof | Risk |
|---|---|---|---|
| A4: verification events are internal beliefs/observations | `bellamem/core/invariants.py`, `bellamem/core/bella.py` | `tests/test_invariants_psi_sim.py::test_a4_verification_event_creates_graph_belief` | Medium |
| A4′: verification payload must be falsifiable (`omega_distance`, `declared`) | `bellamem/core/invariants.py` | `...::test_a4_prime_requires_omega_distance` | Low |
| A4′: later divergence opens conflict against earlier verification belief | `bellamem/core/invariants.py` | `...::test_a4_prime_divergence_opens_conflict_record` | Medium |
| A5: classify historical universal scope at ingestion | `bellamem/core/bella.py`, `bellamem/core/invariants.py`, `bellamem/core/gene.py` | `...::test_a5_scope_classification_marks_historical_universal` | Low |
| A5: anchor gate blocks HU claim by archived contradiction | `bellamem/core/invariants.py` | `...::test_a5_historical_contradiction_blocks_anchor` | Medium |
| A5: conflict mutation cascades HU anchor re-check | `bellamem/core/invariants.py` | `...::test_a5_conflict_registry_mutation_demotes_anchor` | Medium |
| TraversalRecord schema + storage | `bellamem/core/invariants.py`, `bellamem/core/bella.py`, `bellamem/core/store.py` | `...::test_sim_traversal_record_storage` | Low |
| Quarantine isolation from anchor/omega/guard gates | `bellamem/core/invariants.py` | `...::test_sim_quarantine_conflicts_do_not_block_anchor_gate` | Medium |
| Promotion to organic with smoothing + voice-pair rule | `bellamem/core/invariants.py` | `...::test_sim_promotion_to_organic_status` | Medium |
| Demotion back to traversal source | `bellamem/core/invariants.py` | `...::test_sim_demotion_back_to_traversal_status` | Medium |
| Promotion triggers historical anchor re-check | `bellamem/core/invariants.py` | `...::test_sim_promotion_triggers_historical_recheck` | High |
| Instrumentation and audit output | `bellamem/core/invariants.py`, `bellamem/core/audit.py` | `...::test_sim_instrumentation_metrics_and_audit_section` | Medium |
