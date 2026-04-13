"""Scenario harness — synthetic conversations that demonstrate Bella's
entropy reduction and structural preservation under compression.

Each scenario is a self-contained dialogue (a list of `Turn` objects from
`docs/example_session.py`) plus a `test_question` an agent might ask later
and a `must_surface` substring the expand pack should contain. The harness
measures, for each scenario:

  raw_tokens         tokens in the verbatim transcript
  beliefs_in         beliefs after ingest
  entropy_in         Shannon entropy bits of the mass distribution (in)
  beliefs_out        beliefs after age + emerge + prune
  entropy_out        Shannon entropy bits (out)
  expand_tokens      tokens in the expand() pack answering test_question
  surfaced           whether `must_surface` appears in the expand pack
  structure_kept     {disputes, causes, ratifications, self_obs} survived

A note about token compression: small synthetic scenarios (≤30 turns)
do NOT show positive token-compression ratios. Bella's per-belief
metadata overhead (~10 tokens for the `[field] m=0.XX v=N` prefix)
dominates short transcripts. Token compression kicks in at scale —
see `benchmarks/v0.0.4rc1.md` for the 1834-belief case where `expand`
beats `flat_tail` 92% to 0% LLM-judge at the same budget.

What these small scenarios DO demonstrate:

  1. Entropy reduction — Shannon bits of the mass distribution drop
     measurably after age + emerge + prune
  2. Structural preservation — disputes, causes, ratified decisions,
     and self-observations all survive compression untouched
  3. Retrieval correctness — the load-bearing claim from the dialogue
     surfaces in the expand pack when an agent asks the test question
     later, under a tight budget

Run as: python docs/scenarios.py
A pytest smoke test in tests/test_scenarios.py pins the structural
preservation and surfacing assertions so scenarios can't silently
drift when ingest, expand, or prune behavior changes.

Adding a new scenario:
  1. Define a list[Turn] with the dialogue (using the same conventions
     as DIALOGUE in docs/example_session.py — kind/tag/target/lr).
  2. Wrap it in a Scenario(name=..., description=..., dialogue=...,
     test_question=..., must_surface=...).
  3. Append it to SCENARIOS.
  4. Update tests/test_scenarios.py with the expected assertions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from bellamem.core import Bella
from bellamem.core.embed import HashEmbedder, set_embedder
from bellamem.core.expand import expand
from bellamem.core.tokens import count_tokens

from example_session import (
    DIALOGUE as FLAKY_TEST_DIALOGUE,
    Turn,
    age_beliefs,
    compress,
    measure,
    run_dialogue,
)


# ---------------------------------------------------------------------------
# Scenario 2 — the rejected refactor (cross-session dispute survival)
# ---------------------------------------------------------------------------
#
# The agent proposes a refactor that the user has rejected before. The user
# says no with the reason. Bella records the dispute. The story this
# scenario demonstrates: a single user "no" with reasons creates durable
# structure that survives compression — and an agent asking "should I
# refactor X?" tomorrow gets the dispute surfaced via expand(), under a
# tight token budget, without re-asking the question.

REJECTED_REFACTOR_DIALOGUE: list[Turn] = [
    Turn(voice="assistant",
         text="we should extract the auth middleware into a shared base class for v1 and v2",
         tag="proposal",
         lr=1.1),

    Turn(voice="user",
         text="we tried that last quarter and the dependency cycles got much worse",
         tag="cycles_reason",
         lr=2.0),

    Turn(voice="user",
         text="don't pull auth into a base class, leave it duplicated across the two versions",
         kind="deny",
         target="proposal",
         lr=2.0),

    Turn(voice="user",
         text="the duplication is the lesser evil here",
         kind="confirm",
         target="cycles_reason",
         lr=1.8),

    Turn(voice="assistant",
         text="agreed, keeping auth flat across v1 and v2 to avoid cycles",
         tag="agreement",
         lr=1.1),
]


# ---------------------------------------------------------------------------
# Scenario 3 — long debugging session (the token-compression story)
# ---------------------------------------------------------------------------
#
# A realistic 30-turn production incident: a payment webhook failure
# investigation. The transcript carries lots of assistant exposition
# that the filter drops (preamble sentences, demonstratives, fillers)
# while the load-bearing turns — the symptom, the cause chain, the
# rejected workaround, the ratified fix, the self-observation — stay.
#
# Story this scenario demonstrates: when raw transcripts get long
# enough that per-belief metadata overhead stops dominating, the
# expand pack compresses the session by an empirically-measurable
# factor while preserving every load-bearing belief.

LONG_DEBUG_DIALOGUE: list[Turn] = [
    Turn(voice="user",
         text="payment webhook failed in prod again, the third time this week",
         tag="incident",
         lr=2.0),

    Turn(voice="assistant",
         text="let me pull the logs from the last hour and check the failure mode",
         lr=1.1),

    Turn(voice="assistant",
         text="i can see 200ms timeouts in the stripe webhook handler",
         tag="timeout_obs",
         lr=1.2),

    Turn(voice="user",
         text="we keep hitting these timeouts, what's actually going on under the hood",
         lr=1.5),

    Turn(voice="assistant",
         text="the handler issues a synchronous database write before acknowledging the webhook",
         tag="sync_write",
         lr=1.2),

    Turn(voice="assistant",
         text="that database write blocks behind a long-running migration job that runs hourly",
         kind="cause",
         target="timeout_obs",
         lr=1.2),

    Turn(voice="assistant",
         text="we should bump the webhook timeout from 200ms to 2 seconds to give the write room",
         tag="bandaid",
         lr=1.1),

    Turn(voice="user",
         text="no, that's just papering over the real problem and stripe will retry on us anyway",
         kind="deny",
         target="bandaid",
         lr=2.0),

    Turn(voice="user",
         text="we should ack the webhook first then queue the database write asynchronously",
         tag="async_fix",
         lr=2.0),

    Turn(voice="assistant",
         text="that means stripe gets a fast 200 OK and the heavy work happens in a background worker",
         lr=1.1),

    Turn(voice="assistant",
         text="i'll add a job to the redis queue and have the worker process it within the SLA window",
         tag="impl_plan",
         lr=1.1),

    Turn(voice="user",
         text="yes that's the right shape, ack first then enqueue",
         kind="confirm",
         target="async_fix",
         lr=2.0),

    Turn(voice="assistant",
         text="the worker can retry on its own with exponential backoff if the database is still locked",
         tag="retry_logic",
         lr=1.1),

    Turn(voice="assistant",
         text="we should add structured logging around the enqueue path to catch failures early",
         tag="observability",
         lr=1.1),

    Turn(voice="user",
         text="add latency metrics for both the ack path and the worker path",
         lr=1.8),

    Turn(voice="assistant",
         text="i'll patch webhook.py with the new ack-first flow and stripe_worker.py for the queue consumer",
         tag="patch_plan",
         lr=1.1),

    Turn(voice="assistant",
         text="the migration job's lock contention is a separate issue we should track in jira",
         tag="migration_followup",
         lr=1.1),

    Turn(voice="user",
         text="good, file a ticket for the migration lock and tag it for q2",
         lr=1.5),

    Turn(voice="assistant",
         text="this is the third payment incident traced back to synchronous webhook handlers this quarter",
         tag="quarterly_pattern",
         lr=1.05),

    Turn(voice="assistant",
         text="i reach for timeout bumps when the underlying handler architecture is the real problem",
         kind="self",
         lr=1.3),

    Turn(voice="user",
         text="exactly, you keep doing that across different services",
         kind="confirm",
         target="quarterly_pattern",
         lr=2.0),

    Turn(voice="assistant",
         text="i'll add the ack-first pattern to the team handbook so the next webhook handler starts there",
         lr=1.2),

    Turn(voice="user",
         text="yes and link it to the postmortem",
         lr=1.5),

    Turn(voice="assistant",
         text="patched webhook.py with ack-first, added stripe_worker.py with retry, deployed to staging",
         tag="patch_applied",
         lr=1.1),

    Turn(voice="user",
         text="run the integration tests against staging before we promote to prod",
         lr=1.5),

    Turn(voice="assistant",
         text="all integration tests passing in staging, latency p99 dropped from 800ms to 90ms",
         tag="validation",
         lr=1.2),

    Turn(voice="user",
         text="ship it",
         kind="confirm",
         target="async_fix",
         lr=2.0),

    Turn(voice="assistant",
         text="deployed to prod, monitoring the webhook latency dashboard for the next hour",
         lr=1.1),

    Turn(voice="user",
         text="thanks, also document the migration lock as a known issue",
         lr=1.5),

    Turn(voice="assistant",
         text="done, the migration lock is in the runbook and tagged for q2 cleanup",
         lr=1.1),
]


# ---------------------------------------------------------------------------
# Scenario registry
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    name: str
    description: str
    dialogue: list[Turn]
    test_question: str
    must_surface: list[str]   # substrings the expand pack must contain
    expand_budget: int = 800


SCENARIOS: list[Scenario] = [
    Scenario(
        name="flaky-test",
        description="13-turn debugging session: bandaid → rejection → cause "
                    "chain → ratified fix → self-observation",
        dialogue=FLAKY_TEST_DIALOGUE,
        test_question="why does the integration test keep flaking and what's the fix",
        must_surface=["jitter", "rate-limit"],
        expand_budget=600,
    ),
    Scenario(
        name="rejected-refactor",
        description="5-turn refactor proposal that the user rejects with a "
                    "reason from past experience — dispute must survive",
        dialogue=REJECTED_REFACTOR_DIALOGUE,
        test_question="should we refactor the auth middleware into a shared base class",
        must_surface=["cycles", "duplicat"],
        expand_budget=400,
    ),
    Scenario(
        name="long-debug",
        description="30-turn payment webhook incident: rejected timeout bump → "
                    "ack-first async pattern → cause chain → self-observation → "
                    "shipped fix",
        dialogue=LONG_DEBUG_DIALOGUE,
        test_question="how should we handle the payment webhook timeout problem",
        must_surface=["ack", "queue"],
        expand_budget=600,
    ),
]


# ---------------------------------------------------------------------------
# Result row
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    name: str
    description: str
    test_question: str
    raw_tokens: int
    beliefs_in: int
    entropy_in: float
    disputes_in: int
    causes_in: int
    multi_voice_in: int
    self_obs_in: int
    beliefs_out: int
    entropy_out: float
    disputes_out: int
    causes_out: int
    multi_voice_out: int
    self_obs_out: int
    expand_tokens: int
    expand_lines: int
    surfaced: list[str]    # which `must_surface` substrings were found
    missed: list[str]      # which were NOT found (test failure if non-empty)

    @property
    def compression_ratio(self) -> float:
        if self.expand_tokens == 0:
            return float("inf")
        return self.raw_tokens / self.expand_tokens

    @property
    def structure_preserved(self) -> bool:
        """All structural primitives present in→out (none lost)."""
        return (
            self.disputes_out >= self.disputes_in
            and self.causes_out >= self.causes_in
            and self.multi_voice_out >= self.multi_voice_in
            and self.self_obs_out >= self.self_obs_in
        )

    @property
    def all_surfaced(self) -> bool:
        return not self.missed


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _raw_transcript(dialogue: list[Turn]) -> str:
    """Concatenate every turn's text in `voice: text` form, the way a
    flat-tail context window would carry the session."""
    return "\n".join(f"{t.voice}: {t.text}" for t in dialogue)


def run_scenario(scenario: Scenario) -> ScenarioResult:
    set_embedder(HashEmbedder())
    bella = Bella()

    # Phase 1: ingest the dialogue.
    _ingest_dialogue(bella, scenario.dialogue)
    stats_in = measure(bella)

    # Phase 2: age + emerge + prune.
    age_beliefs(bella, days=60)
    compress(bella)
    stats_out = measure(bella)

    # Phase 3: simulate a future-session retrieval. expand() with the
    # scenario's test question against the COMPRESSED graph, under the
    # scenario's budget. We're measuring how many tokens an agent would
    # spend to recover the decisive context.
    pack = expand(bella, scenario.test_question,
                  budget_tokens=scenario.expand_budget)
    pack_text = pack.text()
    expand_tokens = count_tokens(pack_text)
    expand_lines = pack_text.count("\n") + 1 if pack_text else 0

    # Surfacing check: did the load-bearing claims appear in the pack?
    pack_lower = pack_text.lower()
    surfaced: list[str] = []
    missed: list[str] = []
    for needle in scenario.must_surface:
        if needle.lower() in pack_lower:
            surfaced.append(needle)
        else:
            missed.append(needle)

    raw_tokens = count_tokens(_raw_transcript(scenario.dialogue))

    return ScenarioResult(
        name=scenario.name,
        description=scenario.description,
        test_question=scenario.test_question,
        raw_tokens=raw_tokens,
        beliefs_in=stats_in.beliefs,
        entropy_in=stats_in.entropy_bits,
        disputes_in=stats_in.disputes,
        causes_in=stats_in.causes,
        multi_voice_in=stats_in.multi_voice,
        self_obs_in=stats_in.self_observations,
        beliefs_out=stats_out.beliefs,
        entropy_out=stats_out.entropy_bits,
        disputes_out=stats_out.disputes,
        causes_out=stats_out.causes,
        multi_voice_out=stats_out.multi_voice,
        self_obs_out=stats_out.self_observations,
        expand_tokens=expand_tokens,
        expand_lines=expand_lines,
        surfaced=surfaced,
        missed=missed,
    )


def _ingest_dialogue(bella: Bella, dialogue: list[Turn]) -> None:
    """Reimplement run_dialogue's body inline so we can drive it with an
    arbitrary dialogue rather than relying on the module-level DIALOGUE."""
    from bellamem.core import Claim, ops

    tags: dict[str, tuple[str, str]] = {}
    for turn in dialogue:
        if turn.kind == "self":
            claim = Claim(text=turn.text, voice=turn.voice, lr=turn.lr,
                          relation="self_observation")
            result = bella.ingest(claim)
        elif turn.kind in ("deny", "cause"):
            target_field, target_bid = tags[turn.target]  # type: ignore[index]
            claim = Claim(text=turn.text, voice=turn.voice, lr=turn.lr,
                          relation=turn.kind, target_hint=target_bid,
                          target_field=target_field)
            result = bella.ingest(claim)
        elif turn.kind == "confirm":
            target_field, target_bid = tags[turn.target]  # type: ignore[index]
            g = bella.fields[target_field]
            result = ops.confirm(g, target_bid, voice=turn.voice, lr=turn.lr)
            result.field = target_field
        else:
            claim = Claim(text=turn.text, voice=turn.voice, lr=turn.lr)
            result = bella.ingest(claim)

        if turn.tag and result.belief is not None:
            tags[turn.tag] = (result.field, result.belief.id)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def render_markdown(results: list[ScenarioResult]) -> str:
    lines = [
        "# Bella scenarios — entropy reduction, structural preservation, token compression",
        "",
        "Synthetic conversations that demonstrate Bella's compression story",
        "with reproducible numbers. Generated by `docs/scenarios.py`. Pinned by",
        "`tests/test_scenarios.py` so they can't silently drift.",
        "",
        "Read each row as: a dialogue happens, Bella ingests it, time passes,",
        "decay + emerge + prune compress the graph, then a future agent asks",
        "the scenario's test question and gets back an `expand` pack under a",
        "tight token budget. The compression ratio is `raw / expand`.",
        "",
        "**Note on small-scenario token math**: Bella's per-belief metadata",
        "overhead (~10 tokens for the `[field] m=0.XX v=N` prefix) means the",
        "raw vs. expand ratio only flips positive once the dialogue is long",
        "enough that overhead amortizes. The `flaky-test` and `rejected-refactor`",
        "scenarios are short enough that the ratio reads <1×; they demonstrate",
        "**structural preservation**, not token compression. The `long-debug`",
        "scenario is sized to show the token win empirically.",
        "",
        "| scenario | raw | beliefs (in→out) | entropy (in→out) | expand | ratio | structure | surfaced |",
        "|---|---:|---:|---:|---:|---:|:---:|:---:|",
    ]
    for r in results:
        beliefs = f"{r.beliefs_in} → {r.beliefs_out}"
        entropy = f"{r.entropy_in:.2f} → {r.entropy_out:.2f}"
        ratio = f"{r.compression_ratio:.1f}×"
        structure = "✓" if r.structure_preserved else "✗"
        surf = "✓" if r.all_surfaced else f"✗ (missed {r.missed})"
        lines.append(
            f"| `{r.name}` | {r.raw_tokens} | {beliefs} | {entropy} | "
            f"{r.expand_tokens} | {ratio} | {structure} | {surf} |"
        )
    lines.append("")
    lines.append("## What each column means")
    lines.append("")
    lines.append("- **raw**: tokens in the verbatim transcript (flat-tail baseline)")
    lines.append("- **beliefs in→out**: belief count after ingest → after age + emerge + prune")
    lines.append("- **entropy in→out**: Shannon entropy bits of the mass distribution")
    lines.append("- **expand**: tokens in the `expand()` pack answering the test question")
    lines.append("- **ratio**: raw / expand — the compression factor (only meaningful at scale)")
    lines.append("- **structure**: did all disputes, causes, ratifications, and `__self__` "
                 "observations survive compression? (✓ = none lost)")
    lines.append("- **surfaced**: did the load-bearing claims (the scenario's `must_surface` "
                 "substrings) appear in the expand pack? (the future-session retrieval check)")
    lines.append("")
    lines.append("## Scenario detail")
    lines.append("")
    for r in results:
        lines.append(f"### `{r.name}`")
        lines.append("")
        lines.append(r.description)
        lines.append("")
        lines.append(f"- **Raw transcript**: {r.raw_tokens} tokens "
                     f"(verbatim, the flat-tail baseline)")
        lines.append(f"- **After ingest**: {r.beliefs_in} beliefs, "
                     f"entropy {r.entropy_in:.2f} bits "
                     f"({r.disputes_in} disputes, {r.causes_in} causes, "
                     f"{r.multi_voice_in} multi-voice, {r.self_obs_in} self-obs)")
        lines.append(f"- **After compression** (60d age + emerge + prune): "
                     f"{r.beliefs_out} beliefs, entropy {r.entropy_out:.2f} bits "
                     f"({r.disputes_out} disputes, {r.causes_out} causes, "
                     f"{r.multi_voice_out} multi-voice, {r.self_obs_out} self-obs)")
        delta_b = r.beliefs_in - r.beliefs_out
        delta_e = r.entropy_in - r.entropy_out
        if r.beliefs_in:
            pct = 100 * delta_b / r.beliefs_in
            lines.append(f"- **Compression**: {delta_b} beliefs removed "
                         f"({pct:.0f}% reduction), "
                         f"entropy dropped by {delta_e:.2f} bits")
        lines.append(f"- **Structure preserved**: "
                     f"{'yes' if r.structure_preserved else 'NO — load-bearing structure lost'} "
                     f"(every dispute, cause, ratification, and self-obs survived)")
        lines.append(f"- **expand pack**: {r.expand_tokens} tokens, "
                     f"{r.expand_lines} lines — what a future agent sees when "
                     f"asking *\"{r.test_question}\"*")
        lines.append(f"- **Compression ratio**: {r.compression_ratio:.1f}× "
                     f"(raw / expand)")
        if r.all_surfaced:
            lines.append(f"- **Load-bearing claims surfaced**: yes — "
                         f"all of `{r.surfaced}` appear in the pack")
        else:
            lines.append(f"- **Load-bearing claims surfaced**: NO — "
                         f"missing `{r.missed}` from the pack")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(out_path: Path | None = None) -> list[ScenarioResult]:
    out_path = out_path or Path(__file__).parent / "scenarios.md"
    results = [run_scenario(s) for s in SCENARIOS]

    print("=" * 72)
    print(f"{'scenario':<22} {'raw':>6} {'beliefs':>10} "
          f"{'entropy':>14} {'expand':>8} {'ratio':>7}")
    print("=" * 72)
    for r in results:
        print(f"{r.name:<22} {r.raw_tokens:>6} "
              f"{r.beliefs_in:>4} → {r.beliefs_out:<3} "
              f"{r.entropy_in:>5.2f} → {r.entropy_out:<5.2f} "
              f"{r.expand_tokens:>8} {r.compression_ratio:>6.1f}×")
    print()

    out_path.write_text(render_markdown(results), encoding="utf-8")
    print(f"wrote {out_path}")
    return results


if __name__ == "__main__":
    main()
