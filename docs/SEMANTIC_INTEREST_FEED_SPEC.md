# Semantic interest feeds — next-phase product draft

Status: requirements documented; key product decisions approved. Remaining
defaults are assumptions for review, not implementation authorization.
Created: 2026-10-06.

## Goal

Let readers follow research concepts within their selected arXiv categories.
Categories define the search boundary; interest phrases define relevance inside
that boundary. Organize the personalized feed by those interests rather than
generated themes.

The owner confirmed the previous UI refresh, category picker, and session-cookie
fix are deployed. This phase builds on that experience.

## Requirements supplied by the owner

- Allow selection of up to three arXiv categories.
- On the same page, let users enter keywords or phrases separated by semicolons.
- Find semantically related papers, including related ideas and concepts;
  literal occurrence in a title or abstract is neither required nor sufficient.
- Reuse retrieval and semantic processing across users with overlapping
  categories and interests. Do not run the same interest against the same
  category's papers separately for each reader.
- Organize personalized feed sections by keyword or phrase, not by theme.
- Show up to ten most common and ten latest keywords/phrases as clickable pills.
  Clicking a pill adds that interest to the input.
- Owner confirmed on 2026-10-06: interests are optional. Readers without
  interests retain the current category-based feed; readers with interests get
  semantic filtering and sections organized by their phrases.
- Owner revised limits on 2026-10-06: a maximum of five interest phrases per
  reader and three selected categories. These supersede the earlier five-category
  and ten-interest limits. Interests remain optional.
- Owner expects approximately 10–20 readers, each following about five phrases.
  Use this initial audience for capacity evaluation, including both shared and
  distinct interests.
- Owner set a USD $15 daily Gemini usage ceiling on 2026-10-06. Share this
  allowance across public/category summaries, scope creation, semantic matching,
  paper summaries and retries. Use the PaperPulse day in America/New_York;
  reruns do not receive a fresh allowance. Publish available results honestly
  when further work would exceed the ceiling; do not backfill published days.
- Owner confirmed on 2026-10-06: preserve each day's feed with the preferences
  used to publish it. Category and interest changes apply only moving forward;
  do not backfill or rebuild past feeds.
- Owner approved on 2026-10-06: focused semantic matching includes direct
  relevance and closely related methods with a clear substantive connection,
  rather than broad adjacent research.
- Owner approved on 2026-10-06: define and store each normalized interest's
  semantic scope once, shared across readers and categories. Daily matching
  retrieves that scope rather than rediscovering it. If an LLM defines the
  scope, invoke it once per new interest scope version, not per reader or day.
- Owner approved on 2026-10-06: a paper matching multiple interests may appear
  in each relevant section, with an explanation specific to that interest.
  Deduplicate within sections and reuse shared paper summaries.

Example: a reader selects `stat.ML` and `cs.LG`, and enters
`speculative decoding`. Relevant work may discuss draft-and-verify generation,
token acceptance, or related inference techniques without using that exact
phrase. General inference-speed work is not automatically relevant: the
connection must be substantive and explainable.

## Proposed defaults — open to revision

These are working assumptions, not owner-approved decisions.

- Each interest can contain up to 100 characters. Explain phrase-length and
  approved selection limits beside the input; enforce them on the server.
- Every interest applies across all selected categories. No category-to-interest
  mapping UI in this phase. A paper must belong to at least one selected
  category and be relevant to at least one interest.
- Interests are independent: matching any interest qualifies a paper. Users
  need not match every phrase. Compound phrases remain one concept; semicolons
  separate concepts. Commas within a phrase do not split it.
- Preserve the reader's interest order as the section order.
- Match against titles and abstracts initially. Full-paper reading and external
  topic research are outside this phase.
- New or changed preferences take effect in the next daily publishing cycle.
  Saving explains when to expect content; it does not trigger expensive work
  in the web request.
- Preserve existing public Jekyll publishing and access to legacy archives.
- Feedback learning, email, billing, and negative/excluded interests remain
  separate future work.

## Preference editing

Onboarding and settings use the same categories-and-interests form. Show an
example such as `speculative decoding; model compression; uncertainty estimation`.
Save both selections together, retaining entered values when validation fails.
Enforce one to three categories and zero to five interests on the server and in
the picker/input controls. Preserve existing accounts' saved selections and
archives during migration; readers with more than three saved categories must
reduce the selection before their next preference save. Do not silently choose
which categories to remove.

Trim phrases, ignore empty segments, collapse repeated whitespace, and dedupe
case-insensitively. Preserve readable display labels. Clicking a suggestion
appends a phrase with the correct delimiter, avoids duplicates, and never
silently exceeds the limit. Readers can edit or remove any phrase before saving.
Support keyboard use and readable mobile layouts.

Do not automatically merge related but distinct interests. For example,
`model compression` and `quantization` can overlap without being interchangeable.
Normalization of spelling, acronyms, and synonyms needs a separate policy;
exact normalized duplicates are the initial safe reuse boundary.

## Suggestions

Working interpretation:

- Most common means distinct active readers currently selecting an interest,
  counted once per reader, across the service.
- Latest means recently introduced distinct interests that are still selected
  by an active reader, ordered by first introduction. Re-selecting an old phrase
  does not make it new.
- Both lists use normalized identities, display readable labels, and contain
  at most ten entries. Show fewer when fewer qualify; do not invent usage.
- Suggestions do not change selected categories. A suggested interest might
  have no matches in the reader's categories; the UI should make this clear.

**Owner decision — 2026-10-06:** all saved interests are eligible for popular
and latest suggestions. Show only the phrases, never names, profiles, account
identifiers, or links to the readers selecting them. No public opt-in or minimum
popularity threshold is required. Briefly explain beside the input that phrases
may appear as anonymous suggestions to other readers. Do not describe phrases
as confidential; removing account attribution does not guarantee that the text
itself cannot contain identifying details.

## Feed experience

Each interest gets a clearly labeled section. Within it, show a deduplicated list
of relevant papers, with the full title linked to arXiv, a concise plain-language
summary, and a short explanation of why the paper relates to the interest.
The explanation must be grounded in the abstract, not a speculative claim.
Avoid introducing theme headings inside interest sections.

Rank stronger matches first; prefer a short useful list over weak filler. Do not
force a paper into a section simply because it uses the same vocabulary.
No fixed top-N quota is required at this stage; tune relevance and length against
representative examples before launch.

Deduplicate cross-listed papers within each interest. A paper relevant to several
interests may appear under each, with its interest-specific explanation, as
approved by the owner. Reuse the shared paper summary; generate or cache each
distinct interest-specific explanation once, not per reader.

Distinguish these states:

- No relevant papers in a successfully processed daily batch.
- Interest waiting for its first daily processing cycle.
- Source retrieval or matching failed; results are unavailable or incomplete.

Never describe failed processing as “no matches.” Keep archive navigation useful
on days without matches, and show a concise empty state rather than weak content.

Archive entries retain the categories, interest labels, order, and shared result
references used when published. Changing or removing preferences must not alter
past feeds, their section labels, or their availability. Newly added interests
have no historical feed sections; do not backfill them. Existing legacy archive
content remains accessible without reconstructing historical preferences that
were never stored.

Record a small per-reader daily manifest of preference snapshots and shared
result references. This preserves historical assembly without duplicating
matching or generation per reader. Published shared artifacts must remain
stable; future model or prompt changes must not overwrite archived results.

## Efficiency requirements and implementation direction

The product requirement is shared work, not a particular model or database.
Choose the simplest approach that meets semantic quality and measured cost.

1. Fetch each distinct required category once per run, including categories
   needed for public publishing. Reuse those fetched papers for both paths.
2. Identify papers consistently and retain category membership. Cross-listing
   must not cause repeated paper analysis.
3. Maintain a shared normalized interest identity, separate from each reader's
   saved label and order. Store its focused scope: intended concept, included
   related methods, exclusion boundaries, and scope version. Reuse that scope
   across categories, readers, and daily batches. Scope creation is idempotent;
   concurrent submissions of the same normalized phrase share the same work.
   Failed creation remains pending or failed rather than saving an empty scope.
   Scope revisions are deliberate and versioned, never automatic daily expansion.
4. Compute relevance once for each required distinct interest/category/batch
   combination. Readers sharing a combination reuse its result. If readers
   choose `{cs.LG, stat.ML}` and `{cs.LG, cs.AI}`, both reuse the `cs.LG` work.
5. Assemble a reader's feed from shared relevance results, restricted to their
   categories. Do not cache only whole user preference combinations.
6. Reuse paper summaries across sections/readers. Cache an interest-specific
   relevance explanation separately where needed. Serving a feed should not
   require a fresh LLM call.
7. Include input fingerprints and matching/prompt/model versions in cache
   validity. A changed abstract or matching policy must not reuse stale results.
   Preserve successful work across retries; coordinate concurrent jobs.

Candidate approaches to evaluate during technical design include shared paper
embeddings with interest embeddings, or batched LLM relevance classification.
A retrieval-and-reranking hybrid is an option if simpler approaches miss the
quality target. No provider, vector database, or new infrastructure chosen yet.
Benchmark on real examples before selecting a method.

Reuse should scale with distinct papers and distinct interest/category pairs,
not reader count. Distinct interests still create work: enforce the approved $15
daily budget and provider rate limits. Processing drafts may show pending work;
published incomplete days must show partial/unavailable states.

This phase likely needs structured paper and relevance records rather than only
final category Markdown. Retaining titles, abstracts, memberships, and results
would change the old Phase 1 assumption that raw paper data is ephemeral.
Set retention and migration policy explicitly during technical design.

## Quality and acceptance criteria

- A reader can save categories and semicolon-separated interests together.
- Literal matches with unrelated meaning are rejected; substantively related
  papers without the phrase are included.
- Prepare a small reviewed evaluation set including speculative decoding,
  broad interests, ambiguous terms, overlapping interests, cross-listed papers,
  and no-match days. Include positive and negative examples. Agree on acceptable
  misses and irrelevant inclusions before choosing thresholds.
- Two readers sharing an interest/category pair trigger one shared matching
  computation for the same inputs. Partially overlapping selections reuse the
  overlapping work. Retries reuse completed results.
- Each section contains only papers from that reader's categories and explains
  the semantic connection without inventing findings.
- Suggestions obey the eventual visibility/privacy policy; their ordering and
  duplicate handling are deterministic.
- Existing readers without interests keep a working feed. Legacy archives and
  public publishing remain available.
- Failures are distinguishable from empty results. Measure retrieval counts,
  shared cache reuse, matching/generation calls, runtime, and estimated cost.

## Remaining assumptions and technical follow-up

No further product decisions are required to complete this draft. Proposed
defaults remain: 100 characters per phrase, next-cycle activation, matching
titles/abstracts, interest order determining section order, global suggestion
lists ranked as described above, and relevance-first feed length without a
fixed paper quota. Revisit only if evaluation or implementation exposes a
material tradeoff.

Technical design still needs a reviewed relevance evaluation set, a matching
method benchmark, data retention and migration policy, cache/job coordination,
and processing budgets. Choose providers and exact schemas during that work.

This phase introduces explicit interest personalization. The roadmap's previously
planned feedback learning loop remains future work unless the owner changes scope.
