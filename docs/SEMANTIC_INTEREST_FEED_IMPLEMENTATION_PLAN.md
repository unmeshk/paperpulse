# Semantic interest feeds — implementation plan

Status: milestone 0 implemented locally with offline verification; operational activation pending.
Date: 2026-10-06.

Owner-approved review revisions incorporated: shared accounting before paid
evaluation, frozen-run creation before processing, migration-safe release units,
release-matched rollback configuration, and an explicit human evaluation gate.

Sources:

- [Product specification](SEMANTIC_INTEREST_FEED_SPEC.md): approved behavior and constraints.
- [Technical design](SEMANTIC_INTEREST_FEED_TECHNICAL_DESIGN.md): architecture, persistence, failure handling and cost planning.

This plan turns those documents into ordered, reviewable implementation chunks.
Approval to create this document does not execute its code, model calls or rollout.
Keep the existing Python pipeline, FastAPI/Jinja app, SQLite, Gemini integration,
content directory and systemd timer. Add components only where the design requires
them; no queue service, vector database or general job framework.

## Contract to carry through every milestone

- One to three categories and zero to five optional semicolon-separated phrases.
  Preserve existing larger category selections until their next preference save.
- Initial expected use: 20 readers with three phrases each, at most 60 distinct
  interests. Stress case: 20 readers with five distinct phrases each, up to 100.
  The latest workload estimate in the technical design refines the spec's earlier
  five-phrase usage assumption; it does not lower the five-phrase selection limit.
- Semantic matching uses titles and abstracts, a stored focused scope and selected
  category membership. Literal occurrence is neither required nor sufficient.
- Reuse successful scopes, positive/negative paper–interest decisions, generic
  summaries and interest-specific explanations across readers and categories.
- Phrase sections follow reader order; papers can appear under multiple interests
  but only once within each. No themes or weak filler in semantic sections.
- Category-only readers retain category feeds. All newly published personalized
  days use immutable preference snapshots and artifact references.
- Preference changes apply after the next run cutoff. No historical retrieval,
  model processing or changes to published days.
- Show up to ten common and ten latest phrases, with no reader attribution.
- Enforce $15/day total PaperPulse Gemini usage, including public/category work,
  scopes, matching, summaries and retries. Budget days use America/New_York.
- Use one sequential, resumable worker. Remove unconditional 30-second sleeps;
  pace against actual request/token limits and provider feedback.
- Do not treat source/model failure as an empty successful feed. Published partial
  or unavailable sections are terminal for that day.

## Delivery order and dependencies

| Milestone | Depends on | Reviewable result |
| --- | --- | --- |
| 0. Shared model-call and cost controls | Source documents | Schema-independent call boundary enforcing $15/day across production and evaluation |
| 1. Evaluation and capacity baseline | 0 active for all paid calls | Reviewed relevance data, real token/latency measurements, recommended batch size and delivery window |
| 2. Persistence, frozen runs and migration foundation | 1 confirms baseline approach | Additive schema, atomic cutoff/resume lifecycle, and matching deployment/startup changes |
| 3. Shared retrieval and artifact generation | 0–2 | One logical fetch per category; honest completeness and safe public/category retries |
| 4. Preference forms and suggestions | 2 | Complete optional-interest UI, gated until activation |
| 5. Scope, matching and summary worker | 0–3 | Shared semantic processing with bounded, delivery-aware scheduling |
| 6. Daily publication and archive rendering | 2–5 | Immutable feeds in both modes and preserved legacy archive access |
| 7. End-to-end release verification | 0–6 | Passing behavior checks and measured capacity under realistic load |
| 8. Compatible deployment and activation | 7 | Additive rollout, first-day evidence and tested rollback procedure |

Milestone 4 can be developed after 2 independently of processing work, but its
production controls stay disabled until milestone 8. This is a dependency map,
not a requirement to use parallel agents. Keep each change narrow and runnable.

### Safe merge and deployment boundaries

The repository's main-branch workflow deploys changes. A completed milestone is
not automatically a safe independent production release. Use these release units:

- Milestone 0 is independently deployable: existing public/category generation
  uses the shared budget without depending on the semantic schema or activation.
- Milestone 1 adds isolated evaluation tooling; it never starts paid experiments
  automatically in CI or production startup.
- Milestone 2 ships its migration command, deploy-script invocation and compatible
  worker startup together. Never merge startup compatibility checks without the
  migration path that prepares the required schema.
- Milestones 3–6 remain on the feature branch until all existing generation paths
  work with activation off and the complete gated publication path is tested.
  Merge them as one compatible, inactive release after milestone 7. This avoids
  temporarily deploying snapshot consumers without their lifecycle or publisher.
- Milestone 8 activates that tested release. Compatible readers and migrations may
  already be deployed; activation is a separate recorded operational step.

Before the first operational change, compare installed deployment scripts, timer
units and Compose configuration with the repository. Migration notes mention
host-side changes. Record the actual baseline and reconcile differences before
relying on either the local deploy script or existing rollback guide.

## 0. Enforce one shared model-call budget

**Components:** `api/agent.py`, `api/settings.py`, a small dependency-free ledger/
call helper in `api/`, `api/main.py` for the shared lock, and API behavior tests.

Build this foundation before paid evaluation; it requires no new app tables.
Instrument and activate it for existing public/category calls as well as the
evaluation runner. Keep evaluation data isolated, but run paid evaluation through
the same authoritative ledger and lock on the deployment host. A separate local
ledger cannot account for production spending.

Bootstrap accounting at a fresh midnight-Eastern budget day after all previous
untracked generation has finished, or seed verified same-day spend conservatively
before enabling additional paid calls. If earlier spend cannot be established,
wait for the fresh day. During the first operational cutover, pause the timer and
wait for old workers to exit: the old code does not honor the new lock. Resume the
timer once all paid generation uses the shared boundary. No production pause or
deployment is performed by this planning task.

Route all public, category and semantic Gemini calls through one boundary. Preserve
the public thematic prompts while replacing their unconditional sleep with shared
quota accounting. Keep one request in flight and bound request timeouts/retries.
Avoid untracked SDK retries: disable hidden retries or reserve/account for every
possible billable attempt before dispatch.

Persist the authoritative budget/reservation ledger under the shared durable mount,
using atomic replacement and the pipeline lock. It must survive restart and work
when app SQLite is unavailable. Run totals mirror it; neither fallback nor rerun
gets a fresh allowance. Reserve conservative input and maximum billable output
cost before calling, reconcile reported usage, and retain uncertain reservations
after crashes/timeouts. Use verified prices and include thinking tokens.

Distinguish temporary rate limiting, exhausted daily provider quota, invalid
responses and unavailable storage. If budget integrity cannot be established,
stop paid calls. Preserve capacity to summarize accepted papers and finalize feeds.
No charge is required to assemble already cached results. Provide the reservation
mechanism now; calibrate summary capacity in milestone 1 and apply the delivery
scheduler in milestone 5 rather than implementing semantic scheduling here.

**Done when:** calls whose maximum reservation would exceed $15 never dispatch;
successful usage releases unused reservations; ambiguous failures and retries
cannot reset or reuse reserved dollars; all generation paths share the same day.
Midnight-Eastern budget changes do not confuse the provider's Pacific quota reset.
Paid evaluation remains disabled until existing production calls also use this
boundary and the authoritative day's opening balance is established.

**Validation:** deterministic provider responses, real ledger files and controlled
restart/date/failure scenarios. No live calls needed for accounting correctness.

### Milestone 0 implementation evidence — 2026-10-13

- `api/model_budget.py`: explicit initialization, nonblocking pipeline lock,
  atomically replaced and fsynced ledger, integer nanodollar accounting, daily
  reservations and totals, persistent quota counters/cooldowns, and an evaluation gate.
  No app imports or SQLite dependency. Contexts reject cross-thread/process reuse.
- `api/model_calls.py`: the common text generation boundary for public, category,
  and future evaluation callers. SDK retries and automatic tool calling are disabled.
  Three explicit attempts maximum, each with a separate durable reservation;
  HTTP timeouts are 60 seconds and quota waits are bounded to 120 seconds
  per attempt. Unknown usage retains the maximum reservation after restart.
- Token counting includes the full prompt and system instruction through the
  Developer API's `generateContentRequest` count endpoint, plus a 32-token framing
  margin. The generation output cap includes thinking; reconciliation charges both
  visible output and reported thoughts. Standard text prices rechecked 2026-10-13:
  [$0.25/M input and $1.50/M output](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.1-flash-lite).
  [Output-cap semantics](https://ai.google.dev/gemini-api/docs/thinking#token-limits-and-max_output_tokens)
  and [full-request token counting](https://ai.google.dev/api/tokens#request-body)
  checked the same day. No discounts, grounding, tools, media or explicit caches assumed.
- SDK 2.7.0 transport tests exercise actual serialized count/generation requests,
  disabled hidden retries, provider errors and usage parsing without network access.
  Filesystem/process tests cover crashes, reservation/reconciliation write failures,
  concurrent processes, corrupt/missing state, midnight/DST and quota resets.
- Existing public/category callers share one context held across the full pipeline.
  Duplicate invocations skip work. Accounting failures exit nonzero and completed
  batch text can publish without another paid combine. Cross-run artifact checkpoints
  and explicit partial-content presentation remain milestone 3 work.
- The completion-reserve argument exists and is tested; its amount remains zero
  until milestone 1 measurements calibrate it. Requests use 80% of explicitly supplied
  project quotas, with persistent provider feedback for other project usage.
- Verification: `PYTHONPATH=. .venv/bin/python -m pytest api/tests -q`:
  **69 passed**; app suite **54 passed**; `docker compose -f docker-compose.prod.yml config --quiet`
  passed. Production cutover, actual account quota verification and paid
  evaluation are not performed. The operational milestone checkbox below remains open.

### Milestone 0 accounting initialization and cutover

This is a reviewable procedure, not evidence of deployment. Do not merge this
release without preparing initialization: the new pipeline deliberately refuses
to run against an absent ledger. Reconcile installed Hetzner Compose/deploy/timer
configuration first; do not replace newer host configuration with this checkout's
older operational files. Only the API's `GEMINI_BUDGET_DIR` mount setting changes here.

1. Stop the publishing timer and wait for all old pipeline and paid evaluation
   processes to finish. They do not honor the new lock. Prevent old-image invocations
   during and after cutover. Record the production image and matching configuration.
2. Confirm the deployed key's project, current standard prices and actual RPM/TPM/RPD
   limits in the provider console. The ledger pins this release's model/prices;
   a pricing change requires a reviewed code/ledger migration, not clearing state.
3. Deploy the reviewed API with the shared host directory
   `/var/lib/paperpulse/db/model-budget` mounted as `/data/db/model-budget` through
   the existing DB volume. Set `GEMINI_BUDGET_DIR=/data/db/model-budget` for every
   production and paid-evaluation invocation. Ensure the scheduled image matches.
4. Initialize once with verified same-day opening spend, or a future New York date
   with zero opening spend if previous usage cannot be established. For a future
   start, keep all old paid workers stopped until that day. Never seed zero merely
   because this ledger is new. The following variables must be populated with
   reviewed values; this command uses the selected release image, not an arbitrary latest:

   ```sh
   docker compose -f docker-compose.prod.yml run --rm --no-deps api \
     python -m api.model_budget initialize \
     --start-day "$ACCOUNTING_START_DAY" --opening-spend-usd "$VERIFIED_OPENING_SPEND_USD" \
     --rpm "$VERIFIED_RPM" --tpm "$VERIFIED_TPM" --rpd "$VERIFIED_RPD" \
     --untracked-workers-stopped
   ```

5. Inspect `python -m api.model_budget status` in the same API container environment.
   The initializer refuses to overwrite any ledger. For local offline tests, use
   test fixtures; do not point them at production accounting. Any live local
   experiment still needs the authoritative host ledger and shared lock.
6. At/after the start date, restore the timer and verify a controlled production
   invocation or its first scheduled run: public/category artifacts, journal status,
   ledger spend/reservations and quota counters. Confirm every Gemini generation
   uses this boundary and no old processes/images remain. No paid test is implicit
   in the initialization command.
7. Only then enable future paid evaluation through
   `python -m api.model_budget enable-evaluation --production-controls-verified`
   in that same container environment. This records an operator attestation; it
   does not inspect remote deployment state. Evaluation callers must pass
   `purpose="evaluation"` and run on the host's `ModelBudget` context with isolated
   output. This milestone supplies the boundary, not milestone 1's evaluation runner.

Budget days use request-dispatch date in America/New_York. Responses arriving after
midnight settle the original reservation; retries reserve on their own dispatch day.
Provider daily request counters/reset use America/Los_Angeles. Successful usage releases
unused reservation; timeouts, unknown usage and interrupted calls retain it. The `calls`
counter includes unbilled count-token requests conservatively for request pacing.
An over-bound provider usage report records actual spend and halts future paid work.

Back up the ledger along with its persistent volume. Never delete/reinitialize it,
restore an older spend snapshot, manually refund uncertain reservations, or select
a fresh path to resume spending. Missing/corrupt state requires verified accounting
recovery; the worker fails closed. If rollback would restore an unaccounted API,
disable publishing/evaluation instead and retain the ledger until a compatible
release is restored. This milestone does not migrate the app schema or archive.

## 1. Evaluate the simplest matcher and capacity

**Components:** `api/agent.py`, `api/settings.py`, existing RSS paper shape,
and a small isolated evaluation runner/dataset under the existing API test tooling.

Prepare at least 100 reviewed paper–interest pairs across eight or more interests.
Include speculative decoding, close methods, broad and ambiguous phrases, literal
false positives, semantic matches without literal wording, and no-match examples.
Separate calibration and held-out data by paper identity. Review complete daily
candidate sets too; a curated pair set alone does not establish feed precision.

Use the installed `google-genai` client and configured `gemini-3.1-flash-lite`.
Prototype only the structured scope, relevance and generic-summary calls needed
to test the approach. Save scopes and responses so repeated analysis does not
repeat paid calls. Validate exact IDs, enum values, evidence and output bounds.
Start with the design's 25-paper/24,000-character batch bounds, then measure what
actually fits. Compare a larger batch or multiple scopes per call only if needed;
choose the smallest arrangement that meets quality and cost targets.

Use milestone 0's existing call boundary and authoritative ledger for all live
evaluation requests. Count production and evaluation against the same $15 day;
do not create a second experimental allowance. The runner uses isolated content/
data and never writes public posts or user feeds. Perform dataset preparation and
offline validation while accounting activation is pending; only paid calls depend
on its operational readiness.

Measure input/output tokens, billable thinking tokens where applicable, latency,
invalid responses, precision/recall, unsupported statements and total cost. Review
end-to-end output from generated scopes rather than manually perfect scopes only.
Measure representative real batches and project the 20-reader/60-interest workload;
do not spend the full budget solely to imitate every hypothetical reader.

**Done when:** an evaluation results section in this document records dataset
counts, model/prompt versions, reviewed results, sample costs and latency, and
the estimated completion window at 60 and 100 distinct interests. Proposed 90%
precision/80% recall targets remain provisional pending whole-feed review. Confirm
the production project matches the supplied 4,000 RPM / 4M TPM / 150,000 RPD limits.
The forecast of roughly $5/day is a planning assumption; $15 is the ceiling.

**Human review and gate:** the implementer prepares candidate labels, scope/output
examples and measurements. The owner is the default relevance reviewer and final
decision-maker, or may name a domain reviewer. Human review resolves ambiguous
labels; do not use the evaluated model's own labels as the ground truth. Before
scoring the held-out set, record the approved labeling rubric and numeric quality
targets, starting with the proposed 90% precision/80% recall. Keep held-out results
separate from prompt tuning.

Record pass/fail against those targets, reviewed unsupported claims, projected
cost within $15/day and a delivery window acceptable to the owner. The owner
confirms the relevance interpretation and resulting gate decision. If a target
fails, tune on calibration data and retest on fresh held-out examples; do not
silently relax the criterion. Revise the technical design before introducing a
different architecture. Later integrated measurements must reconfirm this gate.

## 2. Add persistence, frozen runs and explicit migrations

**Components:** `app/schema.sql`, `app/db.py`, `app/main.py`, focused persistence
helpers in `api/`, existing `daily_runs`, `scripts/deploy-paperpulse.sh`, image
packaging as needed, and app/API persistence and deployment checks.

Add the logical tables and constraints from the technical design: interests,
user interests, scope versions, immutable paper inputs, category batches, shared
paper–interest results, summaries and per-reader daily feeds. Extend users with
preference revision and legacy selections; extend daily runs with the frozen
processing contract, deadline, status, cursor and accounting metadata.

Implement the run lifecycle now, before retrieval or semantic consumers: acquire
the existing worker lock, atomically create the day's run and draft preference
snapshots, and load that same contract on resumption. Freeze labels, order,
revision, categories, date, deadline and processing versions; reserve required
scope-version identities before model work. Edits/accounts after cutoff wait
for the next run. Retries never resnapshot current preferences, change versions,
reset budgets or reopen a closed day. No network work occurs in the transaction.
Expose this narrow lifecycle to milestones 3 and 5; it does not publish feeds yet.

Finalize fields for generation checkpoints and partial completeness alongside
source status; those are distinct facts. Establish serialized manifest/scope
formats and their versions. Scope/model/prompt settings must be recoverable on
resumption, not represented only by an unrecoverable hash. Give references stable
identities and validate serialized reference integrity before publication.

Use explicit, idempotent, versioned additive migrations and a single migration
entry point in the app image. Existing startup calls `init_db()` and the deployed
app runs two workers: do not let each worker race to apply production migrations.
Deployment runs the migration once; workers verify compatibility. Coordinate with
the pipeline lock, and inspect existing `daily_runs` rows before adding uniqueness.
The API image continues to contain `api/` only and needs no OAuth configuration.

Include the migration deployment path in this same release unit: select the
release's configuration and images, run the one-off migration to successful
completion, then start compatible app workers and check health before allowing
new pipeline work. On failure, do not start incompatible workers or switch the
scheduled API image to that release. An existing worker must finish before the
deployment takes the lock. If deployment holds the lock while invoking its child
migration, use an explicit lock-ownership convention rather than reacquiring the
same lock and deadlocking. Rehearse the actual sequence in isolation.

Make category/interest replacement and revision changes one transaction. Define
shared normalization once as a small dependency-free helper packaged for both
images, without a new service or broad shared library. Align JavaScript behavior
with the server and test Unicode casefolding differences; the server is authoritative.

**Done when:** migration works on a fresh DB and a realistic copy of the existing
schema, repeated migration is harmless, rollback of a failed transaction retains
preferences, and duplicate concurrent interest saves produce one shared identity.
Deleting an account removes selections and personal manifests/drafts. Existing
three-plus category selections and content remain intact.
Concurrent first invocations produce one cutoff and one set of drafts; subsequent
preference edits leave the frozen contract unchanged. An interrupted/retried run
loads that contract, and migration/deployment failure leaves compatible services
available without starting an incompatible scheduled worker.

**Validation:** real temporary SQLite databases, unique/foreign-key constraints,
transaction failure injection and schema compatibility checks. No production writes.

## 3. Unify retrieval and make generation retry-safe

**Components:** `api/main.py`, `api/arxiv_client.py`, `api/feeds.py`, `api/agent.py`,
`api/webs.py`, `api/file_handler.py` where dev cache compatibility requires it,
and existing API retrieval/feed tests.

Fetch fixed public categories first; then fetch additional categories from the
day's frozen preferences. Reuse those papers across public, category and semantic
paths. Return source date and explicit success/empty/failure/no-new-batch status.
Pass the remaining deadline through network timeouts, retry and pacing loops.
Do not make public publication wait behind user-only category failures.

Canonicalize paper identity, retain input revisions and actual feed membership,
and persist successful batches before generation. Keep latest-publication-date
filtering while avoiding repeated delivery of an unchanged consumed batch. Reuse
successful category inputs on restart; never merge identities by paper title.
Preserve useful dev-mode cached-paper behavior without letting an old ungrouped
cache invent category membership or mask source status.

Generate thematic category Markdown only for snapshotted category-only readers.
Have summarization return explicit batch completeness with text; the current
catch-and-continue behavior must not present partial output as complete. Save
successful intermediate results and retry only missing work.

Public and category publication uses the frozen date and atomic writes.
Checkpoint status, content hash, inputs and generation versions. Recover the
public checkpoint from the published post if its sidecar update was interrupted.
Published artifacts are never regenerated by semantic retries. The public-only
path retains its ability to run when personalized SQLite is unavailable, subject
to the same persistent budget controls.

**Done when:** overlapping categories trigger one logical retrieval, public work
survives personalized failures, cross-listing retains membership, an unchanged
source batch creates no duplicate new papers, and a failed generation batch creates
honest partial status. Repeated invocations preserve published file hashes and
reuse successful generation without additional provider calls.

**Validation:** existing API tests plus RSS fixtures, real file outputs, injected
source/model failures and interruptions between artifact/checkpoint writes.

## 4. Add gated preference controls and phrase suggestions

**Components:** `app/routes.py`, onboarding/settings templates, shared category
picker and input markup, `app/static/category-picker.js`, `app/static/app.css`,
and existing app form/browser checks.

Update both forms together: one to three categories, zero to five interests,
100 characters per cleaned phrase, semicolon-only splitting, order preservation
and case/whitespace duplicate handling. Save both selections atomically. Re-render
validation errors with entered values; retain existing CSRF and authentication.
Previously saved larger selections are visible and removable, with a message that
the next save needs at most three categories; never silently truncate them.

Render ten-or-fewer common and latest suggestions through direct SQLite queries.
Use currently selecting distinct readers for popularity and first introduction
for latest; no minimum count, counts displayed, reader links or attribution.
Buttons append a phrase without duplicate or limit violations. Keep the anonymous
suggestion notice, next-cycle activation explanation, keyboard/mobile behavior and
usable plain-input saving without JavaScript.

Interest entry remains unavailable in production until the service-wide activation
record is set in milestone 8. Test mode can exercise the complete form earlier.
Do not build separate preference or suggestion APIs.

**Done when:** limits and normalization agree with server behavior, failed saves
retain input, popular/latest ordering is deterministic, removing the last selector
hides that suggestion, and adding an existing phrase does not reset its introduction
date. Both forms work at mobile widths and with keyboard-only use.

**Validation:** app tests using real SQLite/session/CSRF behavior and the existing
isolated browser harness. Keep the static-response session-cookie regression checks.

## 5. Implement shared semantic work and fair scheduling

**Components:** focused scope/matching/persistence helpers in `api/`,
`api/agent.py`, `api/settings.py`, `api/main.py`, and API semantic-flow tests.

Create a missing scope once per reserved version, validating it before ready.
Store intended concept, close methods, exclusions and ambiguity note; retain
successful scopes across dates, categories and readers. Do not rediscover scope
during daily relevance calls or automatically revise all scopes on deployment.

For each interest, union its followers' frozen categories, deduplicate eligible
paper inputs and classify only cache misses. Store positive and negative results
with the input/scope/matching-version identity. Validate complete exact-ID coverage;
invalid batches are failures, not implicit negatives. Store abstract-grounded
explanations separately from shared generic summaries. Summarize accepted papers
only when their summary-version cache is missing.

Persist round-robin progress across interests. Bound new-scope attempts so ready
interests get service. Interleave missing summaries with matching and reserve
measured completion capacity; retry bounds and budget controls apply throughout.
Pin run versions across resumption and reject unsupported frozen versions rather
than silently mixing policies. The worker uses the shared nonblocking OS lock.

**Done when:** readers sharing an interest trigger one scope definition and one
decision per distinct eligible paper input/version; overlapping categories reuse
work; multiple sections reuse summaries; failed definitions never become empty
ready scopes. Consecutive overloaded days demonstrate delivery of complete papers
and service to ready interests despite repeated failures elsewhere.

**Validation:** deterministic responses for orchestration, real caches/ledger/run
records for restart tests, and the reviewed live-model set for semantic quality.
Mocked decisions do not establish relevance accuracy.

## 6. Publish immutable daily feeds and preserve archives

**Components:** daily orchestration/publishing helpers in `api/`, `app/routes.py`,
feed/archive templates, and app/API lifecycle tests.

Consume the run and immutable draft preference snapshots created in milestone 2.
Do not create a second snapshot or reload current preferences when publishing.
This milestone implements finalization and rendering, building on the existing
cutoff/resume lifecycle.

As each reader's required work completes, materialize references after category
filtering and section deduplication, then atomically publish their manifest.
Category-only readers use the same history-preserving path. At budget/deadline
closure, publish partial/unavailable drafts using persisted successful outputs.
“No matches” requires complete eligible-source and decision coverage. Published
sections never say “pending” or change later. A later invocation can finalize old
drafts but performs no historical fetching or model calls.

Render archives from the authenticated reader's published manifests, including
empty and unavailable days. Interest sections use escaped structured text and
trusted source links; category sections retain raw-HTML-disabled Markdown.
Current preferences, later scope versions and new cache rows do not change old
feed content, labels, order or eligibility. Recheck account existence before
publishing, and cascade personal records on deletion.

Implement legacy access through frozen rollout-time categories for dates before
the activation cutoff. Do not invent historical selections. New accounts receive
no synthetic legacy archive. Missing post-cutoff manifests never fall back to
assembling content using current preferences.

**Done when:** published feeds remain identical after preference changes and later
processing, no cross-reader access or category leakage occurs, empty/error days
remain accessible, and old-day retries issue zero source/model calls. Legacy access
is stable after settings changes, without historical semantic backfill.

**Validation:** compare persisted references and rendered content across edits,
model-version changes and retries; test crash recovery, deletion during processing,
overlapping invocations, missing artifacts and malformed/untrusted text.

## 7. Verify the integrated release

**Components:** existing API/app test suites and browser harness, isolated content
and SQLite fixtures, evaluation evidence, and deployment configuration checks.

Run end-to-end daily processing for category-only and semantic readers with shared,
partially overlapping and distinct preferences. Include the expected 60-interest
scenario and 100-interest stress case, source/model failures, retries, budget
exhaustion, midnight boundaries and more than one consecutive overloaded day.
Use deterministic fixtures to test scale/control flow; use measured live batches
to estimate real latency and cost rather than issuing thousands of redundant calls.

Confirm schema/migration behavior with two app workers, API image independence
from app imports, persistent mounts and permissions, the common lock/ledger, and
public fallback. Rehearse migration, activation-off deployment and rollback using
the actual deployment entry point and matched release configuration, including
failure cases before migration completes or the scheduled image switches.
Set the soft deadline and systemd timeout from measurements,
with time reserved for finalization; retain the existing daily timer initially.

**Done when:** relevant suites and browser checks pass; held-out relevance and
whole-feed results are reviewed; measured/projected delivery fits the chosen
window and $15 budget; and all failure/history invariants have evidence. Update
the cost forecast if measurements differ from $2–$5/day.

Existing suite commands, using temporary app storage to avoid production data:

```sh
PYTHONPATH=. .venv/bin/python -m pytest api/tests -q
DB_PATH=/private/tmp/paperpulse-semantic-check/test.sqlite CONTENT_DIR=/private/tmp/paperpulse-semantic-check/content PYTHONPATH=. app/.venv/bin/python -m pytest app/tests -q
```

Reuse `app/tests/preview_design.py` and `app/tests/browser_design.cjs` for browser
verification with an isolated account. Extend CI's existing API/app jobs; do not
require paid model calls in ordinary CI. No tests have been run for this plan.

## 8. Deploy compatible readers, then activate

**Components:** `scripts/deploy-paperpulse.sh`, `docker-compose.prod.yml`,
systemd service configuration, app migration/activation metadata, and existing
deployment/rollback documentation.

Prepare the concrete deployment changes and release checks before production
activation. Keep existing work intact; implementation follows normal repository
review and deployment authorization. Do not merge or deploy through this plan.

Deployment support was implemented with milestone 2 and rehearsed in milestone 7;
this milestone executes the release and activation procedure rather than first
adding migration ordering. Define each release as matching image tags/digests,
Compose/runtime configuration, deploy-script version and required schema range.
The repository deploy script currently selects images by SHA but resets host
files to `origin/main`; the rollback guide describes a different behavior. Replace
that mismatch with explicit release-matched configuration and test the installed
entry point, after comparing it with the host baseline.

Do not obtain matching configuration by resetting generated blog posts, content,
the database or the spend ledger. Stage versioned deployment assets separately
from mutable data. Preserve original secret references and persistent mounts.

1. Back up SQLite using its backup mechanism and back up content/checkpoints/ledger.
2. Coordinate deployment and the daily worker through the shared lock. Select
   matched release assets, run pending additive migrations once, and start/check
   compatible app workers before allowing the scheduled pipeline to use the release.
3. Deploy both compatible services with entry/publication activation still off.
   Verify health, mounts, budget enforcement and existing public/category behavior.
4. Choose the first enabled daily-cycle cutoff. During a short write-paused window,
   capture existing readers' legacy categories and set the service-wide activation
   record. Enable interest entry and manifest publication together.
5. Verify the first published category-only and semantic days, anonymous suggestion
   behavior, real usage/cost accounting and historical access after a preference edit.

Rollback uses a compatible release that can still read immutable manifests while
disabling new interest entry. Resume unfinished work only within its frozen
contract and open window. Never replace the new archive reader with the old
current-preference reader, drop added tables or rewrite published manifests.
Keep a complete compatible rollback release available before enabling the feature,
including its configuration and deployment entry point, not only its images.
Rollback must accept the existing additive schema, preserve activation/cutoff
metadata, and retain budget spend/reservations; never restore an older ledger and
refund already spent money. Rehearse rollback through the same command used in
production, including rejection of mismatched images/configuration.

**Done when:** first-day evidence demonstrates successful publication, current
cost accounting and stable history; rollback steps have been rehearsed against
isolated complete releases through the real deployment entry point and preserve
published feeds, schema compatibility and recorded spend.

## Evidence to record during implementation

Keep results here rather than create another planning document. Each completed
milestone records: final behavior/change, validation command or reviewed sample,
result, material limitation and any approved design change. Evaluation records
also include batch sizes, input/output usage, dollars, runtime and delivered papers.
Update source documents when evidence changes a design decision.

- [ ] 0. Shared call boundary and $15/day accounting active before paid evaluation.
  Local implementation and offline checks complete; host activation remains pending.
- [ ] 1. Evaluation, human gate decision and capacity baseline recorded.
- [ ] 2. Persistence, frozen-run lifecycle and migration-safe deployment verified.
- [ ] 3. Shared retrieval and safe generation verified.
- [ ] 4. Preference controls and suggestions verified.
- [ ] 5. Shared semantic worker and delivery fairness verified.
- [ ] 6. Immutable publication and archives verified.
- [ ] 7. Integrated release checks and capacity evidence recorded.
- [ ] 8. Compatible rollout and first-day evidence recorded.

## Remaining inputs and limits

The delivery window and summary reserve must be chosen from milestone 1's
measurements. The $5/day forecast and proposed precision/recall targets are not
measured results. Confirm actual production pricing/quota configuration before
paid processing. Surface a material relevance, cost or delivery-time tradeoff to
the owner one at a time; do not silently widen scopes, lower quality or raise $15.
Retention cleanup, embeddings, feedback learning, email and billing remain
outside this implementation unless evidence and a separate scope decision require
them. No further preliminary document is required to begin milestone 0 once
implementation work is authorized.
