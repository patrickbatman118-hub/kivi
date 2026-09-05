# Kivi

## Known Limitations

- Double Metaphone encodes certain phonetically similar sounds differently — notably 'v' and 'w' (e.g. Kivi and kiwi do not share a phonetic code). In these cases the phonetic match guard does not fire. The system does not incorrectly correct the transcript, but it also cannot use phonetic similarity alone to detect the ambiguity. Mitigation: register explicit variants via the memory dashboard.
- Multi-word canonical forms (e.g. 'Sarvam AI') are not matched as a unit — the tokeniser operates on single tokens only. Multi-word terms should be registered as single-token entries where possible (e.g. register 'AI' separately if needed).
- ASR token-level confidence scores are not used — they are not available from the input. Abstention relies entirely on exact variant matching and phonetic hash matching.
- Correction-sourced memory entries always receive category 'custom_spelling' since category cannot be inferred from a diff. Users can update the category via the memory dashboard.
