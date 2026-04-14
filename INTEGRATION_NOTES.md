# PsiCollapse5A + SIMTraversal Integration Notes

## What was integrated

### BELLA core (unchanged foundation)
BELLA keeps its existing core:
- Jaynes accumulation in `Belief.accumulate`
- routing/ingest through `Bella.ingest`
- replay/audit/emerge flows

### PsiCollapse5A (verification hardening)
Added additive invariants:
- **A4**: omega verification is recorded as an internal graph belief (`record_omega_verification`).
- **A4′**: verification payload requires falsifiable content (`omega_distance`, `declared`) and can open conflicts when later divergence appears.
- **A5**: historical universal scope classification, historical contradiction anchor gate, and cascade re-check on conflict registry mutation.

### SIMTraversal (traversal-generated conflict ingestion)
Added additive traversal lifecycle:
- `TraversalRecord` schema + in-memory/snapshot storage.
- traversal conflict quarantine (`source=TRAVERSAL`) isolated from anchor blocking until promotion.
- promotion/demotion rules (voice-pair + recurrence based), including promotion-triggered A5 re-check.
- instrumentation for resolution rate, closure rate, convergence delta, anchor emergence, and guard block attribution.

## Invariants added
- Verification beliefs are first-class beliefs in the graph.
- Verification beliefs are not tautological: they carry falsifiable state.
- Historical universal claims cannot anchor when unsuperseded conflicts contradict them.
- Traversal conflicts in quarantine do not block anchor qualification.
- Promotion to organic status can invalidate existing historical anchors.

## How to validate
1. Run focused invariant tests:
   - `pytest tests/test_invariants_psi_sim.py -q`
2. Run full test suite:
   - `pytest -q`
3. Optional runtime visibility:
   - `bellamem audit` now includes a traversal instrumentation section.
