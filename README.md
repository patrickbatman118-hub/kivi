# Kivi

Kivi is a memory-aware transcript corrector for a speech transcription product. It sits after ASR and LLM formatting, and before the transcript is shown to the user, correcting the formatted output using vocabulary the system has learned specifically for that user — names, project names, product names, jargon, acronyms, and unusual spellings that a generic ASR/LLM pipeline gets wrong every time.

```
ASR output:          ask aditya to review the sarvam kiwi service
Formatted output:    Ask Aditya to review the Sarvam Kiwi service.
Memory-aware output: Ask Aaditya to review the Sarvam Kivi service.
```

The system learns a user's vocabulary two ways — the user explicitly teaches it a term, or the user corrects a transcript and the system diffs the correction to learn from it — and then uses that vocabulary deterministically at correction time. There is no LLM in the correction path: retrieval and the decision to intervene or abstain are both rule-based.

## Architecture

Full detail lives in [`KIVI_CONTEXT.md`](KIVI_CONTEXT.md) (the spec this repo was built against — its seven architectural decisions are locked and were not revisited during implementation). Summary:

- **Storage** — a `vocabulary_entries` table (canonical form, category, status, evidence source, confidence, phonetic hash) with a `vocabulary_variants` table of known bad forms and an `evidence_log` of what triggered each memory. Deletion is a hard delete with DB-level cascade.
- **Retrieval** — two-stage, per token: an exact match against known variants (fast path), then a Double Metaphone phonetic hash match against stored entries. No embeddings, no vector search.
- **Abstention** — the system defaults to not intervening. Only an exact variant match applies a correction. A phonetic match alone is logged as a candidate and abstained on, because it isn't enough evidence the token is actually a bad form of that entry rather than an unrelated word that happens to sound similar. Every decision — apply, abstain, or pass — is logged with a reason.
- **Learning** — two triggers only: an explicit `POST /memory` call, or a word-level diff between an original and corrected transcript (`POST /correct`). Frequency-based learning is designed for in the schema (`confidence: medium`) but deliberately not implemented.
- **Conflicts** — a new entry whose phonetic hash collides with an existing entry (but with a different canonical form) is flagged `needs_review` rather than silently applied or auto-merged.
- **LLM use** — the Gemini API is scoped only to the ASR → formatted-text cleanup step upstream of this system. Nothing in Kivi's retrieval, abstention, or memory management calls an LLM; those decisions are deterministic so they're auditable and reproducible.

## Known Limitations

- Double Metaphone encodes certain phonetically similar sounds differently — notably 'v' and 'w' (e.g. Kivi and kiwi do not share a phonetic code). In these cases the phonetic match guard does not fire. The system does not incorrectly correct the transcript, but it also cannot use phonetic similarity alone to detect the ambiguity. Mitigation: register explicit variants via the memory dashboard.
- Multi-word canonical forms (e.g. 'Sarvam AI') are not matched as a unit — the tokeniser operates on single tokens only. Multi-word terms should be registered as single-token entries where possible (e.g. register 'AI' separately if needed).
- ASR token-level confidence scores are not used — they are not available from the input. Abstention relies entirely on exact variant matching and phonetic hash matching.
- Correction-sourced memory entries always receive category 'custom_spelling' since category cannot be inferred from a diff. Users can update the category via the memory dashboard.
- Frequency-based learning (a memory strengthening automatically after repeated unconfirmed appearances) is designed for in the schema but not implemented — deferred by design, not an oversight.
- Single-user demo system — `user_id` comes from an environment variable, there is no authentication layer.
