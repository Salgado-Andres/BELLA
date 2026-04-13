# Production correctness — ground truth

**Pre-registered** before the validation run. Written 2026-04-13, before
`bellamem reset` and the fresh re-ingest of the current Bella development
session (`853e838e-…jsonl`, ~291 turns, ~35k conversation tokens).

The methodology is deliberate: ground truth BEFORE retrieval, so the
result can't be cherry-picked. Each question has a known answer from
events I (the assistant) lived through during this session. After the
reset + re-ingest, `bellamem expand` is run on each question. For each:

- **in_pack**: does the correct answer appear anywhere in the pack?
- **rank**: at what position (1-indexed)?
- **top_3**: rank ≤ 3?

Aggregate: in-pack rate and top-3 rate. Compared against the synthetic
correctness test's numbers (100% in-pack, 83% top-3) on 6 hand-authored
scenarios. If production-scale correctness holds, these should be
broadly comparable.

## The 10 questions

| # | question | expected answer (short form) |
|---|---|---|
| Q1 | what version of bellamem did we ship today on PyPI | **v0.1.2** |
| Q2 | what's the median compression ratio across real Claude Code projects | **17.6×** (also accept "17" or "median") |
| Q3 | did we decide to run bellamem as a daemon | **no — cron is mathematically equivalent**, deferred until measured |
| Q4 | what did we change the production compression chart y-axis to | **compression ratio** (from expand pack tokens) |
| Q5 | why did we drop the "budget ceiling" framing | the **budget is a parameter**, not an intrinsic limit; "ceiling" misled readers |
| Q6 | what did @Salgado-Andres report in issues #3 and #4 | **#3: Windows UnicodeDecodeError**, **#4: `.graph` saved to cwd when not a git repo** |
| Q7 | what's the synthetic compression curve break-even point | **~214 raw tokens** |
| Q8 | what did the OpenAI vs HashEmbedder rephrasing comparison show | **essentially the same** — the stable core is structural, not embedder-dependent |
| Q9 | which test file did we add the correctness assertion to | **tests/test_scenarios.py** (`test_correctness_all_answers_in_pack_most_in_top_3`) |
| Q10 | what did we decide about issue #5 (tracked-docs ingestion) | **rejected** — graph is downstream of conversation, ingesting docs would create a feedback loop |

## Substring matchers

Each answer is matched by at least one of the following substring patterns
(case-insensitive, applied to the full pack text):

| # | matchers (OR) |
|---|---|
| Q1 | `v0.1.2`, `0.1.2` |
| Q2 | `17.6`, `17×`, `median` |
| Q3 | `daemon`, `cron`, `mathematically equivalent`, `resident` |
| Q4 | `compression ratio`, `log-y`, `ratio on y`, `ratio chart` |
| Q5 | `budget ceiling`, `parameter`, `intrinsic limit`, `misleading` |
| Q6 | `Salgado`, `#3`, `#4`, `Windows`, `UnicodeDecodeError`, `cwd` |
| Q7 | `214`, `break-even`, `break even` |
| Q8 | `HashEmbedder`, `OpenAI`, `structural`, `embedder` |
| Q9 | `test_scenarios`, `correctness`, `test file` |
| Q10 | `#5`, `tracked-docs`, `feedback loop`, `downstream of conversation`, `ingest docs` |

A question scores `in_pack=True` if ANY substring for that question
appears in the pack text. Rank is the 1-indexed line position of the
first matching belief in the ranked pack output.

## Budget

All queries use `bellamem expand --budget 1500` (same budget as the
production compression measurements) against the freshly re-ingested
graph. The embedder is whatever `.env` specifies (OpenAI
text-embedding-3-small). The EW is `hybrid` (regex + gpt-4o-mini), same
as production dogfood.

## Expected outcomes under three hypotheses

- **Optimistic**: all 10 questions in-pack, ≥8/10 top-3. This would
  strongly validate the synthetic correctness test's result.
- **Realistic**: 8-10 in-pack, 5-7 top-3. This would suggest production
  correctness is in the same ballpark but the distributional noise of
  real data pushes some answers further down the ranking.
- **Pessimistic**: <8 in-pack. This would tell us the synthetic
  scenarios are too easy and the classifier/retrieval has real gaps
  on genuine conversation topology.

Any of these is a valid result. This is a pre-registered test — the
outcome report lands in `docs/production-correctness-results.md` after
the run, regardless of whether it's flattering or not.
