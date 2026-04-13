# Production correctness — results

**Pre-registered test**: see `production-correctness-questions.md`. The
10 ground-truth questions were written and committed BEFORE any query
ran, so the result cannot be cherry-picked.

**Setup**: reset `.graph/default.json`, re-ingest `853e838e-…jsonl`
(the current Bella development session, ~291 turns, ~35k conversation
tokens) via `bellamem save` with `BELLAMEM_EW=hybrid` + OpenAI
`text-embedding-3-small`. Fresh graph: **3 fields, 642 beliefs** after
ingest.

**Run date**: 2026-04-13.

## Raw results

Each query used `bellamem expand --budget 1500`. For each question, I
recorded whether a belief containing a pre-registered ground-truth
substring appeared in the pack, and at what 1-indexed rank (by line
position in the ranked pack output). All 10 queries were issued against
the freshly re-ingested graph with no other intervention.

| # | question | in_pack | rank (b=1500) | rank (b=800) | rank (b=400) |
|---|---|---:|---:|---:|---:|
| Q1 | PyPI version shipped today | ✓ | 11 | 11 | — |
| Q2 | median compression ratio | ✓ | 28 | 18 | 10 |
| Q3 | daemon decision | ✗ | — | — | — |
| Q4 | production chart y-axis change | ✓ | 28 | 17 | 9 |
| Q5 | budget ceiling framing drop | ✓ | 26 | 15 | 7 |
| Q6 | @Salgado-Andres issues | ✓ | 8 | 8 | 7 |
| Q7 | synthetic break-even point | ✗ | — | — | — |
| Q8 | OpenAI vs HashEmbedder comparison | ✓ | 26 | 15 | 7 |
| Q9 | test file for correctness assertion | ✗ | — | — | — |
| Q10 | issue #5 tracked-docs decision | ✓ | 32 | 20 | — |

**Aggregate**:

- **in_pack @ budget=1500**: 7/10 (70%)
- **in_pack @ budget=800**: 7/10 (70%)
- **in_pack @ budget=400**: 5/10 (50%)
- **top_3 rate (any budget)**: **0/10 (0%)**

The earlier "100% in-pack" number from the first pass included two
loose substring matches (`daemon` matching a discussion of daemon
*downsides*, `correctness` matching a generic sentence) that aren't
the actual decisions. Tightening the matchers gives the 70% figure
above. The 0% top-3 rate is robust to matcher choice.

## The load-bearing finding

**The top-5 beliefs of every query are identical.** I ran a diagnostic
dump of ranks 1–5 across all 10 questions. In every case the ranking
was:

```
 1. ⊥ "What we've decided - v0.0.4 first (storage split), then v0.1.0 (log-odds decay...)"
 2.   "Scratch dirs go to /tmp via tempfile, never inside the project tree..."
 3.   "But I doubt anyone has wired this into CI yet — v0.1.1 just shipped..."
 4. ⊥ "Don't publish these numbers as benchmarks/v0.1.0.md — they'd be misleading..."
 5. ⊥ "Don't prune aggressively yet — the limbo growth is a symptom of #1..."
```

These are the five highest-mass beliefs in the graph. **They rank identically across all 10 queries because the query text has essentially no effect on the top-5 ordering.** `expand` is returning a fixed "top-by-mass" prefix regardless of what the agent asked.

This is the gap. The ratified decisions from this session are all *somewhere* in the 1500-token pack (at ranks 8-32), but they're buried below 5 mass-dominant beliefs that have nothing to do with any specific query.

## Why the synthetic correctness test scored 83% top-3

The synthetic test runs against hand-authored graphs of 20-60 beliefs. At that size, the ratified decision IS the highest-mass belief (because we wrote dialogues where the user explicitly confirms the decision and nothing else has comparable structural weight). Mass and relevance are correlated by construction.

At 642 beliefs — a real multi-topic session — mass and relevance decouple. The top-5 by mass are cross-session invariants (v0.0.4 ordering, scratch-dir ratification, don't-prune ⊥ dispute). The per-query answers are at ranks 8-32, not 1-3. The synthetic test didn't catch this because it never exercised the decoupling regime.

## Budget sensitivity

At budget=400 (~8–10 beliefs), 5/10 questions lost their ground-truth match entirely. The 5 that survived all landed at ranks 7–10 — the bottom of the pack. At budget=800, the match rate recovers to 7/10 because the pack is large enough to include the rank 8–20 region where real answers live. This confirms that the ranking isn't just slightly-off — **the decisions are systematically buried below the mass-dominant prefix.**

## What this validates vs. what it breaks

| prior claim | validated? | note |
|---|---|---|
| structural preservation under compression | ✓ | the session's beliefs survive ingest and compression |
| 100% in-pack on synthetic correctness test | ✓ (synthetic) | tightened match still 70% in-pack on production |
| 83% top-3 on synthetic correctness test | **falsified on production** | **0% top-3 at any budget** |
| "mass-weighted retrieval beats cosine" (bench) | **context-dependent** | holds on bench's 1834-belief forest where questions matched mass; doesn't hold here |
| decision-bearing core stable under rephrasing | ✓ | but "decision-bearing" = "top-mass", which isn't always the query answer |

The rephrasing-robustness result is still technically correct — the same 5 high-mass beliefs come back for any rephrasing of any query. The stable core is stable because **it's ignoring the query entirely**. That's a different interpretation than the one I wrote into `scenarios.md`, and a less flattering one.

## The honest takeaway

**Bella's `expand` is mass-dominated at production forest sizes and does not rank query-relevant beliefs prominently.** The ratified decisions from today's session are retrievable (in the pack, at ranks 8–32) but not retrievable *prominently* (top-3 rate 0/10). An agent asking "what did we decide about X?" gets back the top-5 cross-session invariants first, not the specific X-decision.

This is the opposite of what the synthetic correctness test implied, and it explains why the LLM-judge bench's 92% number has always felt brittle: on a 1834-belief forest where the bench questions happen to align with mass-dominant beliefs, retrieval works; on a real multi-topic session where mass and query-relevance decouple, retrieval degrades badly.

The synthetic tests weren't wrong, they were too easy. The user was right to push for production validation.

## Possible root causes (not yet investigated)

1. **Mass weight >> relevance weight in `expand()` at large forest sizes.** The weighting was probably tuned on smaller graphs where the two signals were already correlated. At 642 beliefs, the cross-session invariants have high enough mass to dominate per-query cosine.

2. **Cross-session invariants are high-mass because they were ratified over many turns.** This is *correct* behavior for the cross-session case ("what principles apply?") but wrong for the current-session case ("what did we decide today?").

3. **No query-specific reranking after the initial top-K.** `expand` appears to select by mass + small relevance bonus, rather than doing two-pass retrieval (recall-by-cosine, then rerank-by-mass).

4. **The budget is too generous.** At budget=1500, the pack holds ~35 beliefs; the top-5 mass-dominant ones eat the prime real estate. A smaller budget forces more discriminating ranking — but also drops real answers entirely (in-pack @ budget=400 is only 50%).

None of these have been tested yet. This document is diagnostic, not prescriptive.

## Follow-up experiments (in priority order)

1. **Try `bellamem before-edit`** instead of `expand` — it has different weighting (no freshness, different ranking). Does the same query return query-relevant beliefs at the top?

2. **Tune the mass/relevance weight balance** in `core/expand.py` and re-run the same 10 queries. Does the top-3 rate climb? This is the structural fix if the design intent was actually "relevance-driven with mass tiebreak", not "mass-driven with relevance bonus."

3. **Add query-specific reranking**: fetch top-K by cosine, then rerank the K by mass + structural signals. This is a bigger architectural change but would fix the production-correctness problem definitively.

4. **Re-measure the v0.0.4rc1 bench on the current 642-belief forest** with the new classifier. Does `expand` still score 92% LLM judge? If the LLM judge *also* falls off a cliff at this forest size, that's further evidence of the mass-dominance problem. If the LLM judge is still high, then the LLM judge itself is circular in a way this pre-registered test isn't.

5. **Build a larger, multi-topic production corpus** (multi-project ingest) and re-run production correctness at that scale. The current test is one session; cross-session retrieval may behave differently.

## What this DOESN'T mean

- Bella is not useless. The 70% in-pack rate means the correct answer IS stored in the graph and IS retrievable — just not prominently-ranked. An agent willing to process a 35-belief pack would still get the answer.
- The production compression ratios (15 projects, median 17.6×, range 3.6×–90×) are unaffected — they measure token count, not retrieval quality.
- The structural preservation, entropy reduction, and dispute-survival claims all still hold.
- The LLM-judge bench on the v0.0.4rc1 snapshot still stands as a data point for that specific forest state.

What it does mean: **the "92% LLM judge" headline doesn't generalize to real multi-topic sessions under the current expand weighting.** The README's pitch is accurate for the forest it was measured on; it's not (yet) accurate as a general claim.

## Recommendation

Do NOT update the README or any published headline based on this result. This is a dogfood checkpoint and a diagnosis, not a new pitch number. The right next move is to investigate the mass-vs-relevance balance in `expand` and see whether a targeted fix (or a reranking pass) restores the production top-3 rate without regressing the synthetic tests. That's a code change in v0.1.3+ territory, not something to rush.

For now: honest disclosure of the gap in `scenarios.md` (linking to this document), and a new GitHub issue tracking the production-correctness follow-up as v0.1.3 scope.
