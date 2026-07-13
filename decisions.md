# Architecture Decisions

Short, honest entries as each decision gets made. Purpose: capture *why*, not
just *what*, while the reasoning is fresh. This becomes the raw material for
the eventual case-study writeup, and it's a more useful portfolio artifact
than the code alone.

---

## No LangGraph

The pipeline is linear: lease parser -> compliance-diff -> verifier. Each
stage runs once and hands off to the next; nothing decides to branch or loop.

LangGraph earned its place in Groundwork's research mode because the router
node genuinely decided between two real paths (answer from notes vs. trigger
a new search) and could loop. That's the condition that justifies a graph:
real conditional control flow. Forcing this pipeline into LangGraph would add
state-schema and node-wiring overhead for zero control-flow benefit.

Revisit if: we ever add an automatic retry loop (verifier rejects a finding
-> re-run compliance-diff with different retrieval -> re-verify, capped at 1).
That would be a genuine loop and would justify introducing it then, not now.

## No LangChain

Each stage is: build a prompt with specific retrieved context, call the
Claude API directly, parse a structured response. LangChain's abstractions
(prompt templates, generic retrievers, document loaders) exist to remove
boilerplate around patterns we're already handling more precisely ourselves:
psycopg + pgvector gives exact SQL control over jurisdiction-filtered
retrieval, and Claude's native tool-calling gives structured output directly.

Given the core value of this app is citation-grounding accuracy, transparency
into exactly what prompt goes to the model and what comes back matters more
than boilerplate reduction. Direct SDK calls keep that visible; a framework
layer would sit between us and the thing we most need to debug.

## Postgres + pgvector, not a second vector store

Compliance checking needs combined structured filtering (jurisdiction,
citation, effective date) AND semantic similarity search, often in the same
query. Splitting this across a SQL database and a separate vector store
(like Groundwork's ChromaDB) would mean two round-trips and state to keep in
sync. pgvector puts both in one query surface: `WHERE jurisdiction = ...
ORDER BY embedding <-> query_vector`.

## Cross-provider verifier (LiteLLM), same pattern as Groundwork's judge

The verifier checks compliance-diff's factual claims against the actual
retrieved statute/ordinance text -- a grounded check, not a subjective
quality grade, so the self-grading bias risk is smaller than it was for
Groundwork's report-quality judge. But there's still a real correlated-error
risk: if the diff agent misreads a statute a specific way, the same model
verifying its own output could repeat the identical misreading.

Given the stakes here (real legal accuracy for a real landlord, not a
research report's polish) are higher than Groundwork's, we're keeping
genuine cross-provider independence: compliance-diff runs on Claude, the
verifier runs on a different provider via LiteLLM (e.g. GPT-4o-mini -- cheap
and sufficient for a grounded yes/no check against supplied source text).

Alternative considered and rejected: a different Claude model (e.g. Haiku
verifying Sonnet) instead of a different provider. Cheaper and simpler, but
doesn't fully break correlated errors from the same model family. Given the
app's entire premise is "don't trust one model's confident claim alone," the
small added cost of a second provider is worth it here specifically.

## Structured legal entries, not naive whole-document RAG

The simpler alternative would have been to embed the entire statute PDF in
fixed-size chunks and let retrieval + the LLM handle the rest, the same
pattern Groundwork used for arbitrary uploaded documents. We rejected that
here because the two situations aren't equivalent. Groundwork's documents
were unpredictable and the cost of an approximate answer was low. Here, the
source is a small, knowable set of legal rules, and the entire value of the
app depends on exact citations. Naive chunking risks cutting a rule
mid-sentence or merging unrelated sections, naive retrieval risks surfacing
a topically-close but wrong rule, and reverse-engineering a clean citation
out of an LLM-generated answer built from arbitrary chunks is fragile by
construction.

Hand-curating each requirement as its own row costs real upfront effort,
someone has to read the source and identify each discrete rule, but it buys
precision: every chunk is a complete, meaningful unit, and the citation is
exact by construction rather than inferred after the fact. This tradeoff
makes sense because our scope is bounded (one jurisdiction, ~15-20
requirements total), so the fixed manual cost is small and doesn't need to
scale. It would not make sense at 50-state scale, where some hybrid or
automated approach would become necessary just to keep the project
tractable.

## Top-k RAG retrieval over full-context prompting, kept for scalability

At our actual current scale (roughly 20-30 requirements total across all
jurisdiction layers), we could skip embedding-based retrieval entirely for
the compliance-diff step and just place every active requirement's full_text
directly into the prompt. That would remove retrieval-miss risk completely,
since there's no vector distance to get wrong.

We're keeping top-k retrieval anyway, for two reasons. First, a PM-level
design shouldn't optimize only for today's single-city scope when the
mechanism is meant to demonstrate scalable architecture, dumping the entire
requirement set into every prompt is a design that quietly breaks the moment
jurisdiction count grows, and we'd rather build the version that scales from
the start than redo this later. Second, we already have layered defenses
against a bad retrieval: the compliance-diff agent receives the full_text
(not just the summary) of the top-k candidates and can explicitly return "no
matching requirement found" rather than being forced to pick one, and the
verifier layer re-checks the result against the actual retrieved source text
afterward. Retrieval quality is one layer among several, not the sole
safeguard.

Retrieval itself operates on the requirement summaries, not the full_text,
since plain-language summaries match a lease clause's plain-language content
more cleanly than dense statutory wording would. We deliberately retrieve
top-k (not top-1), because near-duplicate summaries are a real, observed
case in our own data (e.g. the residential-scope and anti-waiver clauses
that exist once per section, worded almost identically). Top-1 retrieval
risks silently picking the wrong one of two near-identical candidates,
top-k retrieval surfaces both, and the actual matching decision is deferred
to the LLM comparing full_text, not the embedding step.

## Two-tier requirement/awareness classification

Several sourcing decisions kept forcing a false binary: a legal provision
either mapped cleanly onto a specific lease clause we could check
(compliant/absent/contradicts), or we excluded it entirely, even when it was
a real, useful thing for a landlord to know (e.g. 502-A's common-area duty,
505-A's automatic drug-violation termination right, most of Allegheny
County's Article VI physical/structural standards). Excluding these fully
went against the app's core purpose: surfacing rules a landlord may have
missed, not just checking clause-level compliance.

Added a check_tier column ('requirement' vs 'awareness') to resolve this.
Requirement-tier items are checked against a specific lease clause and go
through the full pipeline: retrieval, diff, verifier. Awareness-tier items
are background legal facts that are true regardless of what the lease says,
they only need a lighter presence check (does the lease address this topic
at all), not a compliance verdict, so they skip the verifier entirely, there
is no claim being made to verify.

Awareness items are only shown if the lease doesn't already address that
topic, surfacing something the landlord already wrote into their lease would
be redundant and would erode trust in the rest of the report. Critically,
when the presence-check is uncertain whether a topic is covered, the default
is to show the item rather than suppress it. This is the awareness-tier
version of the same asymmetric-caution principle already applied to
requirement-tier findings (over-flag rather than under-flag, since a missed
real issue is worse than a landlord seeing one redundant note).

Reclassified 502-A and 505-A from requirement to awareness under this
framework, since neither has a specific lease clause to check against, both
are background rights/duties that apply regardless of lease wording. This
also reopens Allegheny County's Article VI productively: rather than
excluding most of its physical/structural standards as out of scope, they
can now be sourced as awareness-tier entries.

## Pinning direct dependencies isn't enough -- transitive ones can still drift

We deliberately pinned anthropic==0.34.2 in requirements.txt for
reproducibility, but didn't pin httpx, a library anthropic depends on
internally rather than something we call directly. pip installed the newest
available httpx (0.28.1) at install time, which had removed an argument
(`proxies`) that anthropic==0.34.2 still relies on internally, causing a
TypeError at runtime with no connection to anything we wrote.

Fixed by explicitly pinning httpx==0.27.2 in requirements.txt. The lesson:
pinning a package's version doesn't freeze its dependency tree unless every
dependency in that tree is also pinned. For a small project this is usually
fine to catch and fix reactively when it surfaces, as it did here, but it's
worth remembering as a source of "works today, breaks in six months" risk
if this project's dependencies are ever left untouched for a long stretch.

## Real substring-verification debugging story: four distinct root causes, plus one architectural gap

Testing the retrieval-based lease parser against a real lease surfaced a
70% false-positive rate on the "matched_clause_text does not appear as a
substring of any candidate chunk" warning. Rather than loosen the check
(which would have defeated its purpose), we diagnosed each case against
real data before fixing anything, and found four genuinely distinct causes
stacked on top of each other:

1. Curly/smart punctuation differences between PDF-extracted chunk text
   and the model's returned quote (fixed: punctuation normalization).
2. The model silently cleaning up PDF-extraction spacing artefacts, e.g.
   an errant space before a comma (fixed: same normalization pass).
3. pypdf occasionally dropping the space character at a line-wrap
   boundary within the PDF's content stream (e.g. "whichuses" instead of
   "which uses"). Whitespace collapsing cannot fix an absent character;
   fixed with a whitespace-*stripped* comparison used only as a fallback
   when the whitespace-collapsed check fails, logged as an informational
   note rather than a warning when it's what resolves the match.
4. Batching ~25 requirements into one prompt means a chunk retrieved as a
   candidate for one requirement_key is visible in-context to the whole
   batch, so the model sometimes correctly draws on a chunk labeled for a
   different requirement. Fixed by also checking each entry against the
   deduplicated union of every candidate chunk in the batch, not just the
   requirement's own candidate list.

A fifth case remained after all four fixes: the Fair Housing clause
straddles this specific PDF's page 12/13 boundary. document_extract.py
joins extracted pages with "\n\n", and chunk_lease_text's primary split
treats every "\n\n" as a paragraph boundary -- so a PDF page break (a
rendering artefact, not a real paragraph break) gets chunked as if it were
one, splitting a single sentence across two separate chunks with neither
containing the whole thing. The model reconstructed the full sentence
correctly by reading across the boundary; no single-chunk or chunk-union
check we built can verify a match that only exists as a concatenation of
two adjacent chunks. This is a genuine chunking design gap, not a
verification-logic gap.

The broader lesson: when a verification check has a high failure rate,
diagnose against real, reproduced evidence before touching the check
itself. Here that surfaced a mix of genuinely harmless artefacts and one
real, distinct architectural gap, which a single blanket fix (e.g. "just
loosen the substring check") would have hidden rather than addressed.

## Accepted limitation: pypdf occasionally injects layout-label text mid-sentence

After fixing the page-boundary chunking bug (see above), one further case
surfaced: this lease's two-column layout has floating labels (a row label
like "Fair Housing" and a page-number header like "Page 13") that pypdf's
extraction sometimes interleaves into the middle of nearby flowing
paragraph text, rather than keeping them cleanly separate. In the observed
case, this inserted "fair housing page 13" mid-sentence between "based"
and "upon", breaking exact substring verification even though the
underlying legal content was fully correct in every case manually checked.

This is a narrower, different root cause from the page-boundary chunking
issue: it's a text-extraction artefact from this specific PDF template's
two-column layout, not a chunking design flaw. Accepted as a known
limitation rather than fixed further, since generalizing the substring
check to strip arbitrary injected page-number-like tokens from anywhere
mid-string trades real fabrication-detection sensitivity for a
increasingly narrow, cosmetic edge case. Final state: 1 flagged case out
of 48 classified requirements on the test lease, fully diagnosed and
explained, not a mystery. Worth revisiting only if this pattern recurs
meaningfully across other real leases during Phase 6 eval-suite testing.

## Real example: an ambiguous word in a tool description silently broke the verifier

First real run of the verifier produced 7 "not confirmed" findings, but every
one of their notes explicitly endorsed the original compliance-diff verdict
("the conclusion aligns with the identified issue," "the conclusion is
accurate"), while confirmed was still set to false. The tool description's
phrasing -- "confirmed=false if there is a specific discrepancy between the
evidence and the conclusion" -- was ambiguous between two readings: (1) a
discrepancy between what the diff agent concluded and what its own stated
comparison actually supports (the intended meaning, a reasoning-consistency
check), and (2) a discrepancy between the lease and the law (the underlying
legal issue itself). gpt-4o-mini consistently read it as (2): it set
confirmed=false whenever the finding described a real legal problem,
regardless of whether the diff agent's reasoning was actually sound.

Fixed by rewording the tool description and prompt with explicit, unambiguous
language and a worked example distinguishing "the diff agent's reasoning was
flawed" from "the lease has a real problem" -- a correctly-reasoned
'contradicts' about a genuine issue must be confirmed=true. After the fix,
confirmed counts moved from 9/16 to 13/16, and every remaining disputed note
was internally consistent with its own confirmed=false value.

This is a concrete demonstration of why cross-provider verification matters
architecturally, not just in theory: a subtly ambiguous word in our own
prompt caused a systematic, silent misalignment between a model's stated
reasoning and its structured output, on the very agent whose entire job is
catching exactly that kind of silent misalignment elsewhere in the pipeline.
It was only caught because we read the actual note text rather than trusting
the boolean at face value -- the same discipline this project has applied
throughout (never trust a structured field without spot-checking what it
actually represents against real data).

## Automated family grouping and cross-reference extraction over hand-curation

Two eval suite failures traced back to compliance-diff judging every
requirement in total isolation, with no visibility into modifying or
related requirements (e.g. the notice-can-be-shortened clause, 501(e),
never being shown alongside the default notice periods, 501(a)-(b), it's
meant to modify). The fix needed a way to group related requirements and
surface cross-references, but a hand-curated relationship list doesn't
scale: it requires re-reading the corpus by hand every time it grows, and
silently goes stale if source text is ever revised.

Instead: (1) family_key, mechanically derived from each row's own citation
string via regex (511.1(a), 511.1(b), 511.1(c) all resolve to family
"511.1"), grouping same-section subsections automatically; (2)
family_cross_references, populated by parsing full_text for explicit
citation phrases ("in accordance with sections 511.2 and 512") rather than
manual review, since our full_text is primary-source language we already
sourced and verified -- the cross-references are already sitting in the
text itself, not something requiring new legal judgment to discover.

This paid off immediately: automated extraction found two additional real
cross-references (511.2 -> 511.1, both directions) that manual review had
missed. This is direct evidence the automated approach isn't just cheaper
than hand-curation, it's more thorough, since it doesn't depend on a human
happening to notice a specific sentence.

Explicitly considered and rejected: asking the LLM to detect cross-
references dynamically at judgment time instead of extracting them
deterministically ahead of time. Our full_text corpus is small (73 rows),
fixed, and entirely self-authored using a limited, consistent citation
vocabulary -- exactly the condition where a mechanical, auditable, fully
reproducible extraction beats a flexible-but-unverifiable LLM judgment
call re-run on every lease. The same reasoning as the earlier
"hand-curated structured entries over naive whole-document RAG" decision,
applied one level up: know your data, and precision-by-construction wins
when the corpus is small and controlled.