# Semantic baseline evaluation

Milestone 1 preparation, 2026-10-14. No live Gemini calls or relevance review have
been performed. Production accounting activation is pending. This directory is
isolated tooling and public research data; importing it or running tests starts
no evaluation. No application schema or feed publication behavior changes.
`offline-baseline.json` records verified source counts and unmeasured capacity fields.

## Dataset and human review

`dataset.json` contains 128 candidate pairs across eight interests: speculative
decoding, retrieval augmented generation, diffusion language models, alignment,
graph neural networks, uncertainty quantification, knowledge distillation and
reinforcement learning for language models. There are 61 calibration and 67
held-out pairs, split by canonical arXiv identity across input revisions. All
authoritative labels and reviewers are initially empty.

Curated inputs come from the repository's June 3 RSS cache. Selection deliberately
enriches method/literal candidates, near misses and distractors. Notes nominate
cases where the full phrase is absent. Alignment includes ambiguous meanings and
incidental literal wording; diffusion language models includes image/time-series
diffusion near misses. These nominations are not verified positive/negative labels.
Human review must confirm this coverage and resolve ambiguity. Do not estimate
natural feed precision from this curated distribution alone.

Complete October 14 snapshots provide 642 `cs.CL`, 181 `stat.ML` and 742 `cs.CV`
candidate inputs, with 1,521 distinct immutable inputs in their union. Review
speculative decoding, uncertainty quantification and diffusion language models
against those respective complete sets. Archived gzip-compressed raw XML, hashes,
source dates and membership lists permit independent completeness checks.
Calibration papers are excluded from these whole-day sets. Paper identity and
input revision identity remain distinct; category membership is never inferred
from the ungrouped legacy cache.

```sh
PYTHONPATH=. .venv/bin/python -m api.evaluate_semantic validate \
  --dataset api/evaluation/dataset.json --snapshots api/evaluation

# Use a new directory: existing human work is never overwritten.
PYTHONPATH=. .venv/bin/python -m api.evaluate_semantic review-packet \
  --dataset api/evaluation/dataset.json --output /private/tmp/paperpulse-review
```

The packet contains `pairs.csv`, three complete-day CSVs and `rubric.json`.
The owner is the default reviewer or names a domain reviewer. Fill `label` with
`direct`, `close` or `unrelated`; use `note` for disputed cases. Read the complete
title/abstract, not just nomination notes. Predictions are never copied into
ground truth. Review outputs separately for scope correctness and unsupported
claims. Before held-out or whole-day calls, the owner records `approved_by` and
`approved_at` in the rubric, confirms the labeling interpretation, and approves
numeric targets (proposed precision 0.90, recall 0.80). The runner pins this rubric
and prompt hash in those runs. Never tune prompts using held-out results. A
changed prompt needs fresh held-out papers and a new approved rubric.

Import all completed CSVs together, preserving the original dataset:

```sh
PYTHONPATH=. .venv/bin/python -m api.evaluate_semantic import-review \
  --dataset api/evaluation/dataset.json \
  --csv /private/tmp/paperpulse-review/pairs.csv \
        /private/tmp/paperpulse-review/daily-cs.CL-2026-10-14.csv \
        /private/tmp/paperpulse-review/daily-stat.ML-2026-10-14.csv \
        /private/tmp/paperpulse-review/daily-cs.CV-2026-10-14.csv \
  --reviewer 'REVIEWER NAME' --output /private/tmp/paperpulse-reviewed
```

This produces `reviewed-dataset.json`. Blank labels remain unreviewed; no default
negative labels are created. Further review imports require a new destination.
CSV phrase/title/URL/abstract fields must remain identical to the frozen dataset;
edit only labels and notes. Reports also reject changed interest phrases, so old
scopes cannot be scored against renamed interests.

## Baseline and paid-call gate

`api/semantic.py` supplies versioned scope, relevance and generic-summary prompts,
JSON schemas and local validators. Initial batches stop at 25 papers or 24,000
serialized paper-input characters. Oversized individual abstracts fail explicitly
and need a reviewed input bound; they are never truncated into a successful result.
Scope text is bounded to 400 words. Responses require exact IDs, valid enums,
bounded explanations/summaries and verbatim abstract evidence for accepted papers.
This verifies structure and evidence presence, not semantic correctness.

Structured configuration uses installed `google-genai==2.7.0` and configured
`gemini-3.1-flash-lite`; SDK HTTP serialization is checked offline. Model-side
compatibility still needs a real successful call. Reference:
[Gemini structured outputs](https://ai.google.dev/gemini-api/docs/generate-content/structured-output?hl=en),
checked 2026-10-14. No new dependency, embedding index or model architecture added.

**Paid runs require milestone 0's production cutover and evaluation activation.**
Use the production host's authoritative `GEMINI_BUDGET_DIR`, shared persistent
ledger and exclusive lock. Never initialize an experimental ledger, copy an old
ledger or use a separate allowance. Every call uses `purpose="evaluation"`, the
same $15 New York day, explicit retries and conservative reservations. The runner
cannot initialize/reset accounting or enable evaluation. No `--live` means no run.
Commands below are for after activation, in the reviewed host/container environment;
they are not authorization to deploy or call Gemini now.

Place reviewed input/rubric on that host and retain artifacts in a separate
directory, outside source data, public blog/content and the budget directory.
`api/Dockerfile` already copies `api/`, including this tooling. A one-off container
needs a separate persistent evaluation output mount; use its existing budget
mount and secret references. No app/OAuth configuration is required.

```sh
# After accounting activation; use the host's existing Python/container environment.
python -m api.evaluate_semantic run --live \
  --dataset /data/reviewed/reviewed-dataset.json --output /data/evaluation \
  --split calibration --size 25

python -m api.evaluate_semantic run --live \
  --dataset /data/reviewed/reviewed-dataset.json --output /data/evaluation \
  --split heldout --size 25 --rubric /data/reviewed/rubric.json

python -m api.evaluate_semantic run --live \
  --dataset /data/reviewed/reviewed-dataset.json --output /data/evaluation \
  --split whole_day --category cs.CL --size 25 --rubric /data/reviewed/rubric.json
# Repeat whole_day for stat.ML and cs.CV. Compare --size 5/15 only on calibration
# or a separate fresh capacity dataset, if baseline measurements require it.
```

Successful scopes, decisions and summaries are content-addressed by model,
prompt, schema, output cap and full input. Repeating an identical run reuses them;
generic summaries are shared across interests. Raw responses, parsed text,
input/output/thinking usage, attempt latency including pacing, and failures are
saved. Interrupted/invalid calls remain explicit failures; ordinary reruns do not
silently purchase another response. Operator review can authorize another isolated
experiment, still against the same ledger. A crash after response and before
persistence can leave paid work unrecoverable; its ledger reservation remains.

## Analysis, capacity and owner decision

```sh
python -m api.evaluate_semantic report \
  --dataset /data/reviewed/reviewed-dataset.json --output /data/evaluation
python -m api.evaluate_semantic output-review \
  --dataset /data/reviewed/reviewed-dataset.json --output /data/evaluation
```

Reports keep calibration, held-out and complete-day results separate. They show
raw confusion counts, accepted-match and delivered-feed precision/recall with
95% Wilson intervals, missing delivery, real batch sizes, invalid responses,
tokens, thinking, latency and costs. Missing summaries/decisions count as missed
relevant delivery, not dropped examples. `output-review.csv` includes every
generated scope, accepted explanation and generic summary. The reviewer fills
`acceptable` with `yes`/`no` and records inaccuracies in `note`. No self-grading.
Per-run cost attribution includes cached measurements; do not sum it as new spend.
Ledger balances remain authoritative for ambiguous reservations.

Capacity works offline too: without live samples, monetary/runtime projections
remain `null`. Actual captured inputs yield 45, 12 and 55 matching batches per
interest at the 25-paper/24,000-character bounds; the union needs 109. It shows
5/15/25 bounds for both 60 and 100 distinct interests. These counts are not a
latency/cost benchmark or confirmation of the $5 forecast.

For measured projections, supply a quota-evidence JSON with `project`,
`verified_by`, `verified_at` and `limits: {rpm, tpm, rpd}` copied from the deployed
key's provider console. Confirm whether they match the supplied 4000/4000000/150000.
Provide measured public/category production cost and runtime, not the historical
$0.50–$0.80 planning estimate. No secrets belong in evidence files.

```sh
python -m api.evaluate_semantic capacity \
  --dataset /data/reviewed/reviewed-dataset.json --output /data/evaluation \
  --quota-evidence /data/reviewed/quota-evidence.json \
  --production-overhead-usd MEASURED_USD --production-overhead-seconds MEASURED_SECONDS
```

Projection requires real scope/match/summary samples and complete runs from all
three source sizes. It uses the highest observed whole-day acceptance rate,
assumes distinct summaries rather than unmeasured reuse, includes actual pacing
and 80% quota ceilings, and separates cold-scope cost/runtime from steady state.
The all-accepted summary upper bound is reported separately. The sampled scope
and candidate mix may differ from 60/100 real interests; the owner must approve
that extrapolation. The measured maximum summary-call reservation supplies a
completion-reserve starting point for milestone 5. Choose finalization buffer
and delivery window explicitly; the current timer/service are unchanged.

The owner writes a decision JSON containing `decision` (`pass`/`fail`), `reviewer`,
`reviewed_at`, `report_hash` and `capacity_hash` (their `analysis_hash` values),
`candidate_pool` (a named capacity scenario), `delivery_window_seconds`,
`finalization_buffer_seconds`, `batch_size` and `reason` explaining the relevance/capacity decision.

```sh
python -m api.evaluate_semantic gate \
  --dataset /data/reviewed/reviewed-dataset.json --output /data/evaluation \
  --decision /data/reviewed/gate-decision.json
```

The gate rejects missing human labels, incomplete sets/outputs, mismatched review
text or stale measurements, failed approved targets, rejected generated text,
budget/quota overflow or insufficient delivery time. A fail decision records
failures without relaxing targets. Review scope interpretation, zero unsupported
claims and the extrapolation personally; automated validation cannot substitute
for that judgment. Record final live results and owner decision in milestone 1's
implementation-plan evidence section before proceeding to milestone 2.

Whole-day quality is aggregated across the three complete sets. A correctly empty
day has undefined individual precision; it is preserved in aggregate counts,
not rejected solely for delivering no matches. Held-out results remain separate.
Capacity and gate compare the same selected upper batch size, and quota evidence
must match the limits actually used by the measured runs. Measured 95th-percentile
stage latency supplies the window projection; this remains an extrapolation.
