from bellamem.core.bella import Bella, Claim
from bellamem.core.invariants import (
    CONFLICT_ORGANIC,
    CONFLICT_TRAVERSAL,
    DECLARED_DIVERGING,
    DECLARED_LOCAL_OMEGA,
    RESOLUTION_CLOSED,
    RESOLUTION_LOCKED,
    SCOPE_HISTORICAL_UNIVERSAL,
    TRAVERSAL_COMPLETE,
    add_conflict,
    add_traversal_record,
    conflict_pair_hash,
    demote_conflict,
    guard_block_event,
    promote_traversal_conflicts,
    qualify_for_anchor,
    record_omega_verification,
    traversal_metrics,
)


def _belief(b: Bella, text: str, *, lr: float = 1.8, entity_refs=None):
    r = b.ingest(Claim(text=text, voice="user", lr=lr, entity_refs=entity_refs or []))
    assert r.belief is not None
    return r.belief


def test_a4_verification_event_creates_graph_belief():
    b = Bella()
    vb = record_omega_verification(
        b, omega_distance=0.004, declared=DECLARED_LOCAL_OMEGA, cycle_index=7
    )
    assert vb.content["act"] == "omega_verification"
    assert vb.content["omega_distance"] == 0.004
    assert vb.content["declared"] == DECLARED_LOCAL_OMEGA
    assert "__self__" in b.fields
    assert vb.id in b.fields["__self__"].beliefs


def test_a4_prime_requires_omega_distance():
    b = Bella()
    try:
        record_omega_verification(
            b, omega_distance=None, declared=DECLARED_LOCAL_OMEGA, cycle_index=1
        )
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_a4_prime_divergence_opens_conflict_record():
    b = Bella()
    v1 = record_omega_verification(
        b, omega_distance=0.003, declared=DECLARED_LOCAL_OMEGA, cycle_index=10
    )
    v2 = record_omega_verification(
        b, omega_distance=0.08, declared=DECLARED_DIVERGING, cycle_index=11
    )
    conflicts = list(b.conflicts.values())
    assert len(conflicts) == 1
    assert conflicts[0].belief_a == v1.id
    assert conflicts[0].belief_b == v2.id


def test_a5_scope_classification_marks_historical_universal():
    b = Bella()
    blf = _belief(b, "Acme has always been consistent.", entity_refs=["acme"])
    assert blf.scope == SCOPE_HISTORICAL_UNIVERSAL


def test_a5_historical_contradiction_blocks_anchor():
    b = Bella()
    hu = _belief(b, "Acme has always been consistent.", lr=12.0, entity_refs=["acme"])
    hu.recurrence_count = 5

    other = _belief(b, "Acme had a contradiction in 2020.", entity_refs=["acme"])
    add_conflict(b, hu.id, other.id, status="RESOLVED", source=CONFLICT_ORGANIC)

    ok = qualify_for_anchor(b, hu, cycle_index=20)
    assert ok is False
    assert hu.is_anchor is False
    assert hu.anchor_blocked is True
    assert (hu.anchor_blocked_reason or "").startswith("conflict:")


def test_a5_conflict_registry_mutation_demotes_anchor():
    b = Bella()
    hu = _belief(b, "Acme has always followed policy.", lr=20.0, entity_refs=["acme"])
    hu.recurrence_count = 8

    assert qualify_for_anchor(b, hu, cycle_index=3) is True
    assert hu.is_anchor is True

    e = _belief(b, "Acme violated policy in 2021.", entity_refs=["acme"])
    add_conflict(b, hu.id, e.id, source=CONFLICT_ORGANIC)

    assert hu.is_anchor is False
    assert hu.anchor_blocked is True


def test_sim_traversal_record_storage():
    b = Bella()
    a = _belief(b, "alpha", entity_refs=["x"])
    t = add_traversal_record(
        b,
        seed_belief_id=a.id,
        role_sequence=["critic", "synth"],
        conflict_pair_ids=["p1"],
        traversal_beliefs_produced=[a.id],
        resolution_status=RESOLUTION_CLOSED,
        traversal_status=TRAVERSAL_COMPLETE,
    )
    assert t.id in b.traversals


def test_sim_quarantine_conflicts_do_not_block_anchor_gate():
    b = Bella()
    a = _belief(b, "policy outcome stable", lr=20.0, entity_refs=["x"])
    a.recurrence_count = 8
    c = _belief(b, "counter observation", entity_refs=["x"])
    add_conflict(b, a.id, c.id, source=CONFLICT_TRAVERSAL)
    assert qualify_for_anchor(b, a, cycle_index=4) is True


def test_sim_promotion_to_organic_status():
    b = Bella()
    a = _belief(b, "a", entity_refs=["x"])
    c = _belief(b, "c", entity_refs=["x"])

    r1 = add_conflict(
        b, a.id, c.id, source=CONFLICT_TRAVERSAL,
        conflict_voice_a="v1", conflict_voice_b="v2", recurrence_count=3
    )
    add_conflict(
        b, a.id, c.id, source=CONFLICT_TRAVERSAL,
        conflict_voice_a="v3", conflict_voice_b="v4", recurrence_count=3
    )
    promoted = promote_traversal_conflicts(b, cycle_index=9)
    assert r1.id in promoted
    assert b.conflicts[r1.id].source == CONFLICT_ORGANIC


def test_sim_demotion_back_to_traversal_status():
    b = Bella()
    a = _belief(b, "a", entity_refs=["x"])
    c = _belief(b, "c", entity_refs=["x"])
    rec = add_conflict(
        b, a.id, c.id, source=CONFLICT_ORGANIC,
        conflict_voice_a="v1", conflict_voice_b="v2"
    )
    rec.promoted_at = 2
    new_id = demote_conflict(
        b, rec.id,
        recent_resolution_statuses=[RESOLUTION_CLOSED, RESOLUTION_CLOSED, RESOLUTION_LOCKED],
    )
    assert new_id is not None
    assert b.conflicts[rec.id].superseded is True
    assert b.conflicts[new_id].source == CONFLICT_TRAVERSAL


def test_sim_promotion_triggers_historical_recheck():
    b = Bella()
    hu = _belief(b, "acme has always been safe", lr=20.0, entity_refs=["acme"])
    hu.recurrence_count = 7
    assert qualify_for_anchor(b, hu, cycle_index=1) is True

    e = _belief(b, "acme had failure", entity_refs=["acme"])
    rec = add_conflict(
        b, hu.id, e.id, source=CONFLICT_TRAVERSAL,
        conflict_voice_a="r1", conflict_voice_b="r2", recurrence_count=3
    )
    add_conflict(
        b, hu.id, e.id, source=CONFLICT_TRAVERSAL,
        conflict_voice_a="r3", conflict_voice_b="r4", recurrence_count=3
    )
    promote_traversal_conflicts(b, cycle_index=5)

    assert b.conflicts[rec.id].source == CONFLICT_ORGANIC
    assert hu.is_anchor is False
    assert hu.anchor_blocked is True


def test_sim_instrumentation_metrics_and_audit_section():
    b = Bella()
    a = _belief(b, "seed", entity_refs=["z"])
    pair = conflict_pair_hash("x", "y")
    add_traversal_record(
        b,
        seed_belief_id=a.id,
        role_sequence=["r1"],
        conflict_pair_ids=[pair],
        traversal_beliefs_produced=[a.id],
        resolution_status=RESOLUTION_CLOSED,
    )
    add_traversal_record(
        b,
        seed_belief_id=a.id,
        role_sequence=["r2"],
        conflict_pair_ids=[pair],
        traversal_beliefs_produced=[],
        resolution_status=RESOLUTION_LOCKED,
    )
    guard_block_event(b, source=CONFLICT_TRAVERSAL, override_type="SILENT")
    m = traversal_metrics(b)
    assert pair in m["conflict_pair_resolution_rate"]
    assert a.id in m["closure_rate"]
    assert m["guard_block_attribution"]["traversal_blocks"] == 1
