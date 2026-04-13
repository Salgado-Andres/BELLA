"""Smoke + assertion tests for docs/scenarios.py.

Pins each scenario's structural-preservation, surfacing, and (for the
long-debug scenario) token-compression promise. If a future change to
ingest, emerge, prune, or expand silently breaks any scenario's story,
this test fails loudly so the change can be reviewed against the
illustrated mechanism.

The numeric assertions use ranges (not exact values) so the test
tolerates small variation from tokenizer version drift while still
catching real regressions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# docs/scenarios.py imports from example_session, so the docs/ directory
# has to be on sys.path before either module loads.
_DOCS = Path(__file__).resolve().parent.parent / "docs"
if str(_DOCS) not in sys.path:
    sys.path.insert(0, str(_DOCS))


@pytest.fixture
def results():
    """Run all scenarios once per test invocation."""
    from scenarios import SCENARIOS, run_scenario  # type: ignore[import-not-found]
    return [run_scenario(s) for s in SCENARIOS]


def _by_name(results, name):
    for r in results:
        if r.name == name:
            return r
    raise KeyError(f"no scenario named {name!r} in results")


def test_all_scenarios_preserve_structure(results):
    """Every scenario must keep all disputes, causes, ratifications,
    and __self__ observations through compression. None lost."""
    for r in results:
        assert r.structure_preserved, (
            f"scenario {r.name!r} lost load-bearing structure during "
            f"compression: disputes {r.disputes_in}->{r.disputes_out}, "
            f"causes {r.causes_in}->{r.causes_out}, "
            f"multi-voice {r.multi_voice_in}->{r.multi_voice_out}, "
            f"self-obs {r.self_obs_in}->{r.self_obs_out}"
        )


def test_all_scenarios_surface_load_bearing_claims(results):
    """The expand pack must contain every must_surface substring from
    the scenario — the future-session retrieval correctness check."""
    for r in results:
        assert r.all_surfaced, (
            f"scenario {r.name!r} expand pack missed required "
            f"substrings: {r.missed}"
        )


def test_flaky_test_entropy_drop(results):
    """The flaky-test scenario should drop entropy by ≥0.5 bits and
    cut belief count by at least 25% — the README's worked-example
    headline numbers."""
    r = _by_name(results, "flaky-test")
    entropy_drop = r.entropy_in - r.entropy_out
    belief_drop = (r.beliefs_in - r.beliefs_out) / r.beliefs_in
    assert entropy_drop >= 0.5, (
        f"flaky-test entropy drop too small: {r.entropy_in:.2f} -> "
        f"{r.entropy_out:.2f} (drop {entropy_drop:.2f}, expected >= 0.5)"
    )
    assert belief_drop >= 0.25, (
        f"flaky-test belief reduction too small: "
        f"{r.beliefs_in} -> {r.beliefs_out} ({100*belief_drop:.0f}%, "
        f"expected >= 25%)"
    )


def test_long_debug_actually_compresses_tokens(results):
    """The long-debug scenario is sized specifically to show positive
    token compression — raw tokens > expand pack tokens. This pins
    the token-win promise: at scale, Bella expand fits the decisive
    context in fewer tokens than the raw transcript would.
    """
    r = _by_name(results, "long-debug")
    assert r.compression_ratio > 1.0, (
        f"long-debug must show positive token compression "
        f"(raw / expand > 1.0); got raw={r.raw_tokens}, "
        f"expand={r.expand_tokens}, ratio={r.compression_ratio:.2f}"
    )
    # Sanity: the dialogue itself should be substantial.
    assert r.raw_tokens >= 400, (
        f"long-debug raw transcript too short to be a meaningful "
        f"compression test: {r.raw_tokens} tokens"
    )


def test_rejected_refactor_dispute_survives(results):
    """The rejected-refactor scenario's whole point is that a single
    user denial creates a durable dispute. After compression, the
    dispute count must not drop to zero, and the rejection's reason
    must surface in the expand pack."""
    r = _by_name(results, "rejected-refactor")
    assert r.disputes_out >= 1, (
        f"rejected-refactor lost its dispute during compression: "
        f"{r.disputes_in} -> {r.disputes_out}"
    )
    assert "cycles" in [s.lower() for s in r.surfaced], (
        f"rejected-refactor expand pack missing the rejection reason "
        f"(cycles); surfaced={r.surfaced}"
    )
