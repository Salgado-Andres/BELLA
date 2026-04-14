"""PsiCollapse5A + SIMTraversal additive invariants for BELLA core.

This module intentionally layers on top of existing BELLA mechanics with
minimal coupling:
- Beliefs remain the substrate (`core/gene.py`)
- Ingest/routing remains in `core/bella.py`
- Conflict + traversal lifecycle is opt-in via helper APIs here
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .bella import Bella
    from .gene import Belief

SCOPE_STANDARD = "STANDARD"
SCOPE_HISTORICAL_UNIVERSAL = "HISTORICAL_UNIVERSAL"

DECLARED_LOCAL_OMEGA = "LOCAL_OMEGA"
DECLARED_PRE_OMEGA = "PRE_OMEGA"
DECLARED_DIVERGING = "DIVERGING"

CONFLICT_ORGANIC = "ORGANIC"
CONFLICT_TRAVERSAL = "TRAVERSAL"

CONFLICT_UNRESOLVED = "UNRESOLVED"
CONFLICT_SUSPENDED = "SUSPENDED"
CONFLICT_DOMINANT = "DOMINANT"
CONFLICT_RESOLVED = "RESOLVED"

TRAVERSAL_COMPLETE = "COMPLETE"
TRAVERSAL_INVALID = "INVALID"
TRAVERSAL_INDETERMINATE = "INDETERMINATE"

RESOLUTION_CLOSED = "CLOSED"
RESOLUTION_LOCKED = "LOCKED"

N_SEMANTIC_THRESHOLD = 3
M_DEMOTION = 2
P_DEMOTION_WINDOW = 3
K_PROMOTION_PER_CYCLE = 2
BASELINE_WINDOW = 3

UNIVERSAL_MARKERS = {
    "always", "never", "has always", "have always", "had always",
    "has never", "have never", "had never", "at no point",
    "without exception", "every time", "invariably", "throughout",
    "in all cases", "in every case", "at all times", "never once",
    "demonstrated consistently", "at all examined", "without fail",
    "not once", "zero instances of",
}


@dataclass
class ConflictRecord:
    id: str
    belief_a: str
    belief_b: str
    status: str = CONFLICT_UNRESOLVED
    dominant_belief: Optional[str] = None
    cycle_count: int = 0
    tension_level: str = "LOW"
    created_at: int = 0
    last_evaluated: int = 0
    superseded: bool = False
    superseded_by: Optional[str] = None
    source: str = CONFLICT_ORGANIC
    conflict_voice_a: Optional[str] = None
    conflict_voice_b: Optional[str] = None
    traversal_id: Optional[str] = None
    recurrence_count: int = 0
    promoted_at: Optional[int] = None
    entity_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "belief_a": self.belief_a,
            "belief_b": self.belief_b,
            "status": self.status,
            "dominant_belief": self.dominant_belief,
            "cycle_count": self.cycle_count,
            "tension_level": self.tension_level,
            "created_at": self.created_at,
            "last_evaluated": self.last_evaluated,
            "superseded": self.superseded,
            "superseded_by": self.superseded_by,
            "source": self.source,
            "conflict_voice_a": self.conflict_voice_a,
            "conflict_voice_b": self.conflict_voice_b,
            "traversal_id": self.traversal_id,
            "recurrence_count": self.recurrence_count,
            "promoted_at": self.promoted_at,
            "entity_refs": list(self.entity_refs),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConflictRecord":
        return cls(
            id=str(d.get("id") or ""),
            belief_a=str(d.get("belief_a") or ""),
            belief_b=str(d.get("belief_b") or ""),
            status=str(d.get("status") or CONFLICT_UNRESOLVED),
            dominant_belief=d.get("dominant_belief"),
            cycle_count=int(d.get("cycle_count") or 0),
            tension_level=str(d.get("tension_level") or "LOW"),
            created_at=int(d.get("created_at") or 0),
            last_evaluated=int(d.get("last_evaluated") or 0),
            superseded=bool(d.get("superseded", False)),
            superseded_by=d.get("superseded_by"),
            source=str(d.get("source") or CONFLICT_ORGANIC),
            conflict_voice_a=d.get("conflict_voice_a"),
            conflict_voice_b=d.get("conflict_voice_b"),
            traversal_id=d.get("traversal_id"),
            recurrence_count=int(d.get("recurrence_count") or 0),
            promoted_at=d.get("promoted_at"),
            entity_refs=list(d.get("entity_refs") or []),
        )


@dataclass
class TraversalRecord:
    id: str
    seed_belief_id: str
    role_sequence: list[str]
    conflict_pair_ids: list[str]
    traversal_beliefs_produced: list[str]
    resolution_status: str
    traversal_status: str = TRAVERSAL_COMPLETE
    shared_context_hash: Optional[str] = None
    agent_config_hashes: list[str] = field(default_factory=list)
    created_at: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "seed_belief_id": self.seed_belief_id,
            "role_sequence": list(self.role_sequence),
            "conflict_pair_ids": list(self.conflict_pair_ids),
            "traversal_beliefs_produced": list(self.traversal_beliefs_produced),
            "resolution_status": self.resolution_status,
            "traversal_status": self.traversal_status,
            "shared_context_hash": self.shared_context_hash,
            "agent_config_hashes": list(self.agent_config_hashes),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TraversalRecord":
        return cls(
            id=str(d.get("id") or ""),
            seed_belief_id=str(d.get("seed_belief_id") or ""),
            role_sequence=list(d.get("role_sequence") or []),
            conflict_pair_ids=list(d.get("conflict_pair_ids") or []),
            traversal_beliefs_produced=list(d.get("traversal_beliefs_produced") or []),
            resolution_status=str(d.get("resolution_status") or RESOLUTION_LOCKED),
            traversal_status=str(d.get("traversal_status") or TRAVERSAL_COMPLETE),
            shared_context_hash=d.get("shared_context_hash"),
            agent_config_hashes=list(d.get("agent_config_hashes") or []),
            created_at=int(d.get("created_at") or 0),
        )


def classify_scope(text: str, entity_refs: list[str]) -> str:
    t = (text or "").lower()
    has_marker = any(m in t for m in UNIVERSAL_MARKERS)
    if has_marker and bool(entity_refs):
        return SCOPE_HISTORICAL_UNIVERSAL
    return SCOPE_STANDARD


def apply_scope_classification(belief: "Belief") -> None:
    if belief.scope_override:
        return
    belief.scope = classify_scope(belief.desc, belief.entity_refs)


def _find_belief(bella: "Bella", belief_id: str) -> Optional["Belief"]:
    for g in bella.fields.values():
        b = g.beliefs.get(belief_id)
        if b is not None:
            return b
    return None


def conflict_pair_hash(belief_a_id: str, belief_b_id: str) -> str:
    lo, hi = sorted((belief_a_id, belief_b_id))
    return hashlib.sha1(f"{lo}|{hi}".encode("utf-8")).hexdigest()[:12]


def _union_entities(bella: "Bella", a: str, b: str) -> list[str]:
    out: list[str] = []
    for bid in (a, b):
        blf = _find_belief(bella, bid)
        if not blf:
            continue
        for e in blf.entity_refs:
            if e not in out:
                out.append(e)
    return out


def add_conflict(
    bella: "Bella",
    belief_a: str,
    belief_b: str,
    *,
    status: str = CONFLICT_UNRESOLVED,
    source: str = CONFLICT_ORGANIC,
    cycle_index: Optional[int] = None,
    conflict_voice_a: Optional[str] = None,
    conflict_voice_b: Optional[str] = None,
    traversal_id: Optional[str] = None,
    recurrence_count: int = 1,
) -> ConflictRecord:
    now = int(cycle_index if cycle_index is not None else getattr(bella, "current_cycle", 0))
    rec = ConflictRecord(
        id=uuid.uuid4().hex[:12],
        belief_a=belief_a,
        belief_b=belief_b,
        status=status,
        source=source,
        created_at=now,
        last_evaluated=now,
        conflict_voice_a=conflict_voice_a,
        conflict_voice_b=conflict_voice_b,
        traversal_id=traversal_id,
        recurrence_count=recurrence_count,
        entity_refs=_union_entities(bella, belief_a, belief_b),
    )
    bella.conflicts[rec.id] = rec
    bella.conflict_version += 1
    on_conflict_registry_update(bella)
    return rec


def historical_contradiction_check(bella: "Bella", belief: "Belief") -> tuple[bool, Optional[str]]:
    if belief.scope != SCOPE_HISTORICAL_UNIVERSAL:
        return True, None
    entities = set(belief.entity_refs)
    if not entities:
        return True, None
    for rec in bella.conflicts.values():
        if rec.superseded:
            continue
        if not entities.intersection(rec.entity_refs):
            continue
        return False, f"conflict:{rec.id}"
    return True, None


def conflict_blocks_anchor(bella: "Bella", belief_id: str) -> bool:
    """Quarantined traversal conflicts are excluded per SIMTraversal."""
    for rec in bella.conflicts.values():
        if rec.superseded:
            continue
        if belief_id not in (rec.belief_a, rec.belief_b):
            continue
        if rec.source == CONFLICT_TRAVERSAL:
            continue
        if rec.status in {CONFLICT_UNRESOLVED, CONFLICT_SUSPENDED, CONFLICT_DOMINANT}:
            return True
    return False


def qualify_for_anchor(
    bella: "Bella",
    belief: "Belief",
    *,
    min_mass: float = 0.80,
    min_recurrence: int = 3,
    cycle_index: Optional[int] = None,
) -> bool:
    if belief.mass <= min_mass:
        return False
    if belief.recurrence_count < min_recurrence:
        return False
    if conflict_blocks_anchor(bella, belief.id):
        return False
    if belief.anchor_void_until_cycle is not None and cycle_index is not None:
        if cycle_index <= belief.anchor_void_until_cycle:
            return False
    if belief.scope == SCOPE_HISTORICAL_UNIVERSAL:
        ok, reason = historical_contradiction_check(bella, belief)
        if not ok:
            belief.anchor_blocked = True
            belief.anchor_blocked_reason = reason
            belief.anchor_blocked_at = cycle_index
            belief.is_anchor = False
            belief.anchor_cycle = None
            return False
    belief.anchor_blocked = False
    belief.anchor_blocked_reason = None
    belief.is_anchor = True
    belief.anchor_cycle = cycle_index
    return True


def on_conflict_registry_update(bella: "Bella") -> None:
    for g in bella.fields.values():
        for b in g.beliefs.values():
            if b.scope != SCOPE_HISTORICAL_UNIVERSAL or not b.is_anchor:
                continue
            ok, reason = historical_contradiction_check(bella, b)
            if not ok:
                b.is_anchor = False
                b.anchor_blocked = True
                b.anchor_blocked_reason = reason
                b.anchor_blocked_at = getattr(bella, "current_cycle", 0)


def record_omega_verification(
    bella: "Bella",
    *,
    omega_distance: float,
    declared: str,
    cycle_index: int,
) -> "Belief":
    from .bella import Claim

    if declared not in {DECLARED_LOCAL_OMEGA, DECLARED_PRE_OMEGA, DECLARED_DIVERGING}:
        raise ValueError("declared must be LOCAL_OMEGA, PRE_OMEGA, or DIVERGING")
    if omega_distance is None:
        raise ValueError("omega_distance is required (A4′)")

    claim = Claim(
        text=f"omega verification {declared} d={omega_distance:.6f}",
        voice="system",
        lr=1.2,
        relation="self_observation",
        entity_refs=["__omega__"],
        event_time=time.time(),
        extras={
            "act": "omega_verification",
            "omega_distance": float(omega_distance),
            "declared": declared,
            "cycle_index": cycle_index,
        },
    )
    result = bella.ingest(claim)
    belief = result.belief
    if belief is None:
        raise RuntimeError("failed to record verification belief")
    belief.content.update(claim.extras)
    belief.source_kind = CONFLICT_ORGANIC

    prev = getattr(bella, "last_verification_belief_id", None)
    if prev and declared == DECLARED_DIVERGING:
        prev_belief = _find_belief(bella, prev)
        if prev_belief is not None:
            prev_declared = str(prev_belief.content.get("declared") or "")
            if prev_declared in {DECLARED_LOCAL_OMEGA, DECLARED_PRE_OMEGA}:
                add_conflict(
                    bella,
                    prev_belief.id,
                    belief.id,
                    source=CONFLICT_ORGANIC,
                    cycle_index=cycle_index,
                    conflict_voice_a="system",
                    conflict_voice_b="system",
                )

    bella.last_verification_belief_id = belief.id
    bella.current_cycle = cycle_index
    return belief


def add_traversal_record(
    bella: "Bella",
    *,
    seed_belief_id: str,
    role_sequence: list[str],
    conflict_pair_ids: list[str],
    traversal_beliefs_produced: list[str],
    resolution_status: str,
    traversal_status: str = TRAVERSAL_COMPLETE,
    shared_context_hash: Optional[str] = None,
    agent_config_hashes: Optional[list[str]] = None,
) -> TraversalRecord:
    rec = TraversalRecord(
        id=uuid.uuid4().hex[:12],
        seed_belief_id=seed_belief_id,
        role_sequence=list(role_sequence),
        conflict_pair_ids=list(conflict_pair_ids),
        traversal_beliefs_produced=list(traversal_beliefs_produced),
        resolution_status=resolution_status,
        traversal_status=traversal_status,
        shared_context_hash=shared_context_hash,
        agent_config_hashes=list(agent_config_hashes or []),
        created_at=int(getattr(bella, "current_cycle", 0)),
    )
    bella.traversals[rec.id] = rec
    return rec


def _voice_pairs_for_hash(bella: "Bella", pair_hash: str) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for rec in bella.conflicts.values():
        if rec.superseded or rec.source != CONFLICT_TRAVERSAL:
            continue
        if conflict_pair_hash(rec.belief_a, rec.belief_b) != pair_hash:
            continue
        out.add((rec.conflict_voice_a or "", rec.conflict_voice_b or ""))
    return out


def promote_traversal_conflicts(
    bella: "Bella", *, cycle_index: int, limit: int = K_PROMOTION_PER_CYCLE
) -> list[str]:
    promoted: list[str] = []
    candidates = [
        c for c in bella.conflicts.values()
        if c.source == CONFLICT_TRAVERSAL and not c.superseded
    ]
    candidates.sort(key=lambda c: c.recurrence_count, reverse=True)
    for rec in candidates:
        if len(promoted) >= limit:
            break
        pair_hash = conflict_pair_hash(rec.belief_a, rec.belief_b)
        voices = _voice_pairs_for_hash(bella, pair_hash)
        if rec.recurrence_count < N_SEMANTIC_THRESHOLD:
            continue
        if len(voices) < 2:
            continue
        rec.source = CONFLICT_ORGANIC
        rec.promoted_at = cycle_index
        promoted.append(rec.id)
        # Mid-cycle anchor block per SIMTraversal §8.2
        for bid in (rec.belief_a, rec.belief_b):
            b = _find_belief(bella, bid)
            if b is None:
                continue
            b.anchor_void_until_cycle = cycle_index
        on_conflict_registry_update(bella)
    return promoted


def demote_conflict(
    bella: "Bella",
    record_id: str,
    *,
    recent_resolution_statuses: list[str],
) -> Optional[str]:
    rec = bella.conflicts.get(record_id)
    if rec is None:
        return None
    if rec.source != CONFLICT_ORGANIC or rec.promoted_at is None:
        return None
    if rec.status not in {CONFLICT_UNRESOLVED, CONFLICT_SUSPENDED}:
        return None
    window = recent_resolution_statuses[:P_DEMOTION_WINDOW]
    closed = sum(1 for s in window if s == RESOLUTION_CLOSED)
    varies = len({s for s in window if s in {RESOLUTION_CLOSED, RESOLUTION_LOCKED}}) > 1
    if closed < M_DEMOTION and not varies:
        return None

    rec.superseded = True
    new_rec = add_conflict(
        bella,
        rec.belief_a,
        rec.belief_b,
        source=CONFLICT_TRAVERSAL,
        cycle_index=getattr(bella, "current_cycle", 0),
        conflict_voice_a=rec.conflict_voice_a,
        conflict_voice_b=rec.conflict_voice_b,
        traversal_id=rec.traversal_id,
        recurrence_count=0,
    )
    rec.superseded_by = new_rec.id
    bella.demoted_conflict_count += 1
    return new_rec.id


def guard_block_event(
    bella: "Bella", *, source: str, override_type: str
) -> None:
    bella.guard_blocks.append({"source": source, "override_type": override_type})


def traversal_metrics(bella: "Bella") -> dict:
    pair_stats: dict[str, dict[str, int]] = {}
    seed_complete: dict[str, list[str]] = {}
    for t in bella.traversals.values():
        if t.traversal_status != TRAVERSAL_COMPLETE:
            continue
        if t.resolution_status == TRAVERSAL_INDETERMINATE:
            continue
        seed_complete.setdefault(t.seed_belief_id, []).append(t.resolution_status)
        for pid in t.conflict_pair_ids:
            d = pair_stats.setdefault(pid, {"total": 0, "closed": 0})
            d["total"] += 1
            if t.resolution_status == RESOLUTION_CLOSED:
                d["closed"] += 1

    resolution_rate = {
        pid: (d["closed"] / d["total"] if d["total"] else 0.0)
        for pid, d in pair_stats.items()
    }

    closure_rate: dict[str, float] = {}
    convergence_delta: dict[str, float] = {}
    for seed, statuses in seed_complete.items():
        n = len(statuses)
        if n == 0:
            continue
        closed = sum(1 for s in statuses if s == RESOLUTION_CLOSED)
        cr = closed / n
        closure_rate[seed] = cr
        b = statuses[:BASELINE_WINDOW]
        if b:
            baseline = sum(1 for s in b if s == RESOLUTION_CLOSED) / len(b)
            convergence_delta[seed] = cr - baseline

    traversal_anchor_count = 0
    organic_anchor_count = 0
    traversal_beliefs = {
        bid
        for t in bella.traversals.values()
        for bid in t.traversal_beliefs_produced
    }
    for g in bella.fields.values():
        for b in g.beliefs.values():
            if not b.is_anchor:
                continue
            if b.id in traversal_beliefs or b.source_kind == CONFLICT_TRAVERSAL:
                traversal_anchor_count += 1
            else:
                organic_anchor_count += 1

    def _corr(src: str) -> float:
        events = [e for e in bella.guard_blocks if e.get("source") == src]
        if not events:
            return 0.0
        silent = sum(1 for e in events if e.get("override_type") == "SILENT")
        return silent / len(events)

    return {
        "conflict_pair_resolution_rate": resolution_rate,
        "closure_rate": closure_rate,
        "convergence_delta": convergence_delta,
        "anchor_emergence": {
            "traversal_anchor_count": traversal_anchor_count,
            "organic_anchor_count": organic_anchor_count,
        },
        "guard_block_attribution": {
            "organic_correction_rate": _corr(CONFLICT_ORGANIC),
            "traversal_correction_rate": _corr(CONFLICT_TRAVERSAL),
            "organic_blocks": sum(1 for e in bella.guard_blocks if e.get("source") == CONFLICT_ORGANIC),
            "traversal_blocks": sum(1 for e in bella.guard_blocks if e.get("source") == CONFLICT_TRAVERSAL),
        },
        "quarantined_conflicts": sum(
            1
            for c in bella.conflicts.values()
            if c.source == CONFLICT_TRAVERSAL and not c.superseded
        ),
        "promoted_conflicts_lifetime": sum(
            1
            for c in bella.conflicts.values()
            if c.promoted_at is not None
        ),
        "demoted_conflicts_lifetime": bella.demoted_conflict_count,
    }
