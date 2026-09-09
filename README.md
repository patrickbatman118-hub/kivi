# Kivi

## 1. What this is

Kivi is a speech transcription product built by Sarvam. It turns spoken audio into text through three stages: raw ASR output (lowercase, unpunctuated, and prone to acoustic errors), a formatted version cleaned up by a language model, and a memory-aware version corrected against the user's own vocabulary. This system implements that last stage.

```
ASR output:          ask aditya to review the sarvam kiwi service
Formatted output:    Ask Aditya to review the Sarvam Kiwi service.
Memory-aware output: Ask Aaditya to review the Sarvam Kivi service.
```

The problem exists because ASR fails predictably on exactly the words that matter most to a given user — their own name, the names of colleagues, the projects and products they talk about, the acronyms specific to their work. These words are rare or absent in the ASR model's training data, so the model has no way to know that "Aditya" should have been "Aaditya," or that "Kiwi" should have been "Kivi." No amount of general-purpose ASR improvement fixes this, because the correct spelling is a fact about this particular user, not about the language.

This system's job is to give the transcription pipeline a way to know that fact — without becoming something else in the process. It is not a general personal-memory assistant, and it does not try to learn everything about the user; it stores a narrow, specific class of vocabulary (person names, organisation and project names, product names, technical terms, acronyms, custom spellings), decides when it has enough evidence to correct a transcript with that vocabulary, and — just as importantly — decides when to leave the transcript alone. Replacing a word incorrectly introduces an error that did not exist in the original transcription. I built the system around the premise that this is worse than doing nothing at all, and every other design decision follows from treating silence as the default, safe outcome rather than an exception.

## 2. Architectural decisions

### Decision 1 — What to remember

I considered three options: a narrow vocabulary of proper nouns and custom terms; a broader model of personal facts (preferences, habits, relationships, topics); or everything the ASR happened to struggle with.

The broader personal-facts model turns this into a different product — a general memory assistant with a different risk surface and scope. Recording everything the ASR struggles with is worse: ASR struggles with background noise, disfluencies, and one-off terms that should never be remembered, so that option pollutes the index almost immediately.

I chose to store only the narrow class: person names, organisation names, project names, product names, technical terms, acronyms, and custom spellings (`CategoryEnum` in `app/models/vocabulary.py`). This is the smallest scope that solves the actual problem — words whose correct written form matters to this specific user — without pulling in the risks of the broader alternatives. I rejected vector databases, semantic embeddings, and general fact storage outright, not just deprioritised them.

### Decision 2 — When to learn

I considered four options: explicit user input only; a frequency threshold (N occurrences before persisting); a single correction promoting a term immediately; or a hybrid — explicit input and manual corrections persist immediately, frequency-based evidence requires confirmation first.

Explicit-only input requires upfront effort the user won't always give. A single correction promoting immediately is dangerous on its own — a mistyped correction becomes a permanent memory with no safeguard. A frequency threshold risks committing temporary or one-off terms as if they were established vocabulary. The FTC's case against Amazon over Alexa is the cautionary example here: Amazon's implicit, always-on collection pipeline led to retaining data users believed had been deleted, and aggressive learning thresholds carry the same shape of risk — false memories accumulating from ordinary usage, with no clean way to know they got there.

I chose the hybrid, but only implemented half of it: explicit input (`POST /memory`) and manual-correction detection (`POST /correct`, diffed in `app/services/correction.py`) are the two live triggers — both are treated as high confidence (`ConfidenceEnum.high` in both `add_memory` and `apply_learning`). I designed the schema to support frequency-based learning as well (`ConfidenceEnum.medium` exists specifically for this) but deliberately didn't implement it — shipping an uncalibrated learning system risks the exact index-pollution failure mode described above, and the right threshold can't be picked without real usage data.

### Decision 3 — How a memory is represented

I considered three options: a flat string map (`{"Aaditya": true}`); a structured record with provenance; or a vector embedding.

A flat map can't support correction, conflict detection, staleness tracking, or any explanation of why the system believes something — when it's wrong, there's nothing to inspect or fix. A vector embedding is the wrong representation for this problem entirely (see Decision 4).

The structured record (`VocabularyEntry` in `app/models/vocabulary.py`) is what I implemented: `canonical_form`, `category`, `status` (`active` / `suppressed` / `needs_review` / `deleted`), `evidence_source` (`explicit_input` / `manual_correction`), `confidence`, `created_at`, `last_seen_at`, and `phonetic_hash`, plus a `vocabulary_variants` table of known bad forms and an `evidence_log` table recording what triggered each entry (`trigger_type`, the original ASR/corrected text, session id). Provenance is the point: when a memory turns out to be wrong, you need to know where it came from in order to correct or delete it responsibly.

### Decision 4 — How memories are retrieved

I considered four options: exact string match only; Double Metaphone phonetic hash match; fuzzy string match (edit distance / SymSpell); vector or semantic search.

Rejecting vector search was the most important call I made in this decision. Vector databases capture semantic similarity — words that mean similar things. This is not that problem: "Kivi" and "Keevee" are phonetically similar but semantically unrelated, and a vector search would not find that match at all. The task is acoustic correction, and semantic embeddings are the wrong tool for it regardless of infrastructure cost.

I implemented retrieval as two stages, run per token in `app/services/retrieval.py`. Stage 1 checks for an exact, case-sensitive match against a known variant or canonical form — the fastest path, and the only one that can lead to an applied correction. Stage 2 computes the Double Metaphone code of the token (`app/services/phonetic.py`) and checks it against every stored entry's `phonetic_hash`; a hit here is a candidate, never an application. I check both the primary and secondary Double Metaphone codes of the incoming token against each entry's stored (primary-only) hash, because the canonical form's primary code can turn up as the token's secondary code — e.g. "Adithya" hashes to `('AT0', 'ATT')` while "Aaditya" hashes to `('ATT', '')`, and only checking the token's primary code would miss that match entirely.

### Decision 5 — When memory is applied (abstention logic)

This was the most consequential decision I made. Given a match, should it be applied?

Always applying on any match (exact or phonetic) causes over-biasing: if "Adithya" phonetically resembles "Aaditya," blindly applying the correction could rewrite a different person's name into the wrong one — introducing an error where none existed. I considered and designed for LLM arbitration for ambiguous phonetic matches, but deferred it: it adds latency and hallucination risk without a guaranteed accuracy gain.

What I implemented, in `app/services/pipeline.py`, is tiered:
- Exact variant match → **APPLY** (the user, or a prior correction, has already confirmed this bad form maps to this canonical form) — unless the matched entry's status is `suppressed` or `needs_review`, in which case it's **ABSTAIN** instead, even though the match itself was exact.
- Phonetic match only, not a known variant → **ABSTAIN**, logged as a candidate, never applied — this holds regardless of the matched entry's status, because the reason for not applying is that the token isn't an established variant, not anything to do with the entry's state.
- No match at all → **PASS**, transcript unchanged.

Every one of these three outcomes is logged with an explicit reason in the `intervention_log`; it's a first-class output of `POST /process`, not a debug artifact, so a reviewer can inspect exactly why the system did or didn't act on every token. A system that never intervenes has zero false positives and zero value; a system that intervenes on any match has high recall and an unacceptable false-positive rate. I treat exact variant match as the line where evidence becomes unambiguous enough to act on.

### Decision 6 — Conflicting and stale memories

I considered four options: silent last-write-wins; versioned history; flagging the conflict for the user to resolve; confidence decay over time.

Silent overwrite can break existing, correct behaviour without any signal that it happened. Versioned history adds storage and retrieval complexity disproportionate to the problem. Confidence decay needs a calibrated decay function and a background job to enforce it — I deferred it for the same reason I deferred frequency-based learning: no real usage data to calibrate against yet.

What I implemented is conflict-flagging: when a new entry's phonetic hash collides with an existing entry for the same user (checked in both `add_memory` in `app/routers/memory.py` and `apply_learning` in `app/services/correction.py`), the new entry is created with `status = needs_review` rather than being auto-merged or silently accepted, and `POST /memory` reports it back as a 409 with the conflicting entry's id. The system does not auto-resolve; a `needs_review` entry is never applied by the retrieval pipeline until a person resolves it. `last_seen_at` is updated on every applied correction (`app/services/pipeline.py`); the field exists precisely so staleness-decay logic has something to read from later, even though that logic isn't built yet.

### Decision 7 — User control and deletion

I considered four options: bulk delete only; per-term management through a dashboard; implicit correction detection; the dashboard and correction detection combined.

Bulk-only deletion fails the moment exactly one memory is wrong and the rest are fine. Correction detection alone is invisible — a user has no way to see or manage what the system has quietly learned, which erodes trust in exactly the way the product is trying to avoid.

I implemented both together: `app/routers/memory.py` exposes list, add, status update (`suppressed` / `active`), delete, and reset, all rendered in the demo UI (`app/static/index.html`); `app/routers/correction.py` handles the implicit side via diffing. Deletion is a **hard delete**, not a status flag — `DELETE /memory/{id}` calls `db.delete(entry)` directly, and I enforce the cascade to `vocabulary_variants` and `evidence_log` at the database level via `ondelete="CASCADE"` foreign keys (`app/models/vocabulary.py`), not just through the ORM. This traces directly back to the FTC's $25M settlement with Amazon over Alexa: the finding there was that deleting raw audio while retaining transcripts and derived metadata in secondary tables did not constitute deletion. A deleted memory in this system leaves no row behind in any of its three tables.

## 3. What the system can and cannot do

Kivi can learn a user's vocabulary two ways — through an explicit `POST /memory` call, or by diffing a correction the user makes to a transcript — and apply that vocabulary deterministically at transcription time with no LLM in the decision path. It corrects a token only when that exact bad form has previously been registered as a variant of a canonical entry; anything less certain than that is either logged as a candidate and left alone, or passed through untouched. Every decision made against every token is logged with a specific reason, so a reviewer can see not just what changed but why, and why everything else didn't.

It cannot match multi-word canonical forms as a single unit — the tokeniser in `app/services/pipeline.py` operates on individual whitespace-delimited tokens, so a canonical form like "Sarvam AI" cannot be recognised as one entity. Registering the individual words as separate entries is the only current workaround; fixing this properly would require n-gram tokenisation, which I did not build.

It does not use frequency as a signal. A word the ASR mangles repeatedly without ever being explicitly corrected will never be promoted to a memory on its own; the schema supports it (`ConfidenceEnum.medium` is reserved for exactly this) but I deliberately never calibrated or shipped the threshold that would trigger it, to avoid the index-pollution failure mode frequency-based learning is prone to.

It does not use ASR confidence scores to decide whether to intervene at all — a system with access to per-token ASR confidence could skip correction entirely on spans the ASR is already certain about, but that signal isn't present in the input this system receives, so abstention relies entirely on variant and phonetic matching.

Its phonetic matching is only as good as Double Metaphone, which was designed for English phonology. It will underperform on Tamil, Hindi, and other Indian-language names — directly relevant to Sarvam's actual user base — and there is a concrete, demonstrated gap even within English: Double Metaphone encodes "v" and "w" differently, so "Kivi" and "kiwi" do not share a phonetic code at all (`('KF', '')` vs `('K', '')`), and the phonetic-match guard simply doesn't fire for that pair. This does not cause an incorrect correction — the failure mode is silence, not a wrong edit — but it does mean the system cannot flag that ambiguity to a user the way it can for names that do collide phonetically.

It does not use an LLM to arbitrate ambiguous phonetic matches using sentence context — I designed for a "judge-editor" pattern that would let the system resolve some phonetic-only matches by reading the surrounding sentence, but explicitly deferred it, because it introduces latency and hallucination risk that a fixed candidate list doesn't fully constrain away.

Memories created from a correction diff always get the category `custom_spelling`, because a category cannot be inferred from a before/after word pair alone (`app/services/correction.py`); a user can change it afterward through the memory dashboard, but nothing infers it automatically.

Finally, this is a single-user demo: `user_id` is read from an environment variable and there is no authentication layer, by design, not as an oversight left over from time pressure.

## 4. Architecture overview

```
                     asr_output
                          │
             (formatted_output given?)
                 no │           │ yes
                    ▼           │
            Gemini formats it   │
                    │           │
                    └─────┬─────┘
                          ▼
                formatted_output
                          │
              tokenise (whitespace split,
              strip leading/trailing
              punctuation per token)
                          │
                          ▼
        ┌─── per token ──────────────────────────┐
        │  Stage 1: match in memory?              │
        │     canonical match → PASS              │
        │       (token is already correct)        │
        │     exact variant match:                │
        │       status active → APPLY             │
        │       status suppressed/needs_review    │
        │                      → ABSTAIN          │
        │     no Stage 1 match ↓                  │
        │  Stage 2: phonetic hash match?          │
        │     yes → ABSTAIN (candidate only)      │
        │     no  → PASS                          │
        └────────────────────────────────────────┘
                          │
                          ▼
      memory_aware_output + intervention_log
      (every token's decision + reason)
```

`POST /process` (`app/routers/pipeline.py`) runs this whole flow. Retrieval and abstention are deterministic and never call an LLM; Gemini is invoked only for the one upstream step of turning raw ASR text into formatted text, and only when `formatted_output` is omitted from the request — anyone who supplies it directly bypasses Gemini entirely, which is also how the evaluation suite gets reproducible runs regardless of API availability.

Learning is a separate, decoupled flow. `POST /correct` (`app/routers/correction.py`, logic in `app/services/correction.py`) takes an original and a corrected transcript, diffs them word-by-word, and for each one-to-one word replacement either adds a new variant to an existing entry or creates a new one — flagging it `needs_review` first if its phonetic hash collides with something that already exists for that user.

## 5. Evaluation

I wrote the test cases in `evaluation/cases.json` before the corresponding implementation existed, rather than curating them afterward from cases the system happened to handle well — the brief is explicit that a post-hoc selection of successful examples doesn't count as an evaluation.

I grouped cases into seven categories: **C1** correct interventions (the system should apply a correction), **C2** correct abstentions (the system should stay silent — the category the brief treats as most important, since it's the one a naive "always correct on any match" system fails completely), **C3** explicit learning, **C4** correction-triggered learning, **C5** conflict detection, **C6** user control (suppress, delete, reset), and **C7** edge cases (empty input, all-tokens-match, punctuation handling, multi-word forms).

`evaluation/run_eval.py` drives every case against the live API and reports precision, recall, and abstention correctness separately, because precision and recall alone don't capture the failure mode this system is actually built around. A system that never intervenes has perfect abstention correctness and zero recall; a system that intervenes on every match has perfect recall and zero abstention correctness. Reporting abstention correctness on its own is what makes that tradeoff visible instead of averaging it away.

The script does not call Gemini — every case supplies `formatted_output` directly, so results are reproducible regardless of model availability or rate limits (`docker compose exec app uv run python evaluation/run_eval.py`; results land in `evaluation/results.json`).

Three cases are worth calling out specifically, because I found or worked through them during development rather than having them be obvious from the spec on day one:
- **C2_02** (a phonetic match on a token that turns out to share its *secondary* Double Metaphone code with an entry's primary code, e.g. "Adithya" against "Aaditya") was a real retrieval bug I found during development — Stage 2 originally checked only the token's primary code — and is now fixed and covered by this case.
- **C2_05** ("kiwi" against a memory for "Kivi") is a documented algorithm limitation, not a bug: Double Metaphone encodes "v" and "w" differently, so the two never share a code even checking both primary and secondary. The expected outcome is PASS, not ABSTAIN — the system doesn't have evidence of a match to abstain on, but it also doesn't incorrectly correct anything, so the outcome is still safe.
- **C7_04** (a multi-word canonical form) I exclude from pass/fail scoring entirely, per the documented tokeniser limitation described in Section 3.

## 6. AI use

Architecture and all seven decisions above were made by the developer, working from a locked architectural context document that explicitly forbade the implementing model from proposing alternatives. Claude (claude.ai) was used for research synthesis earlier in the process — summarising how production systems (ChatGPT, Copilot, Apple Intelligence, Gemini, Alexa) handle personalised memory, and surfacing failure modes such as the Amazon FTC case and the over-biasing risk described in Decisions 2 and 5 — and for pressure-testing the reasoning behind each decision. The decisions themselves are the developer's judgment calls, not the model's.

Code was written using Claude, primarily through the Claude Code CLI, with architectural decisions pre-specified in a locked context document at the start of each session and specific, scoped tasks given one at a time. The model implemented what it was told to build; it was not asked to design the system, and instructions to it were explicit that it should not.

Evaluation cases were designed by the developer, before the corresponding code existed, per Section 5. Claude was used to review the case set for completeness and coverage gaps, not to invent the cases themselves.

This README was written using the reasoning developed throughout the project. Claude assisted with drafting and structure, cross-checked against the actual codebase (`app/services/pipeline.py`, `app/services/retrieval.py`, `app/services/correction.py`, `app/models/vocabulary.py`) so that every claim above is one the code actually supports.
