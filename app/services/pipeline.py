import re
import uuid
from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.services.retrieval import load_user_memory, retrieve_memory_for_token
from app.models.vocabulary import VocabularyEntry

def strip_punctuation(token: str) -> Tuple[str, str, str]:
    """
    Strips leading and trailing punctuation from a token.
    Returns (prefix, core_word, suffix)
    """
    match = re.match(r'^([^\w]*)(.*?)([^\w]*)$', token)
    if match:
        return match.group(1), match.group(2), match.group(3)
    return "", token, ""

async def process_transcript(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    asr_output: str, 
    formatted_output: str
) -> Tuple[str, List[Dict[str, Any]]]:
    
    if not formatted_output.strip():
        return "", []

    user_memories = await load_user_memory(db, user_id)
    
    tokens = formatted_output.split()
    memory_aware_tokens = []
    intervention_log = []
    
    entries_to_update = set()

    for raw_token in tokens:
        prefix, core_word, suffix = strip_punctuation(raw_token)
        
        if not core_word:
            memory_aware_tokens.append(raw_token)
            continue
            
        entry, match_type = retrieve_memory_for_token(core_word, user_memories)
        
        decision = "PASS"
        reason = "No match found in memory"
        final_core_word = core_word
        
        if match_type == "canonical":
            decision = "PASS"
            reason = "Token matches canonical form exactly \u2014 already correct, no intervention needed"
        elif match_type == "exact_variant":
            if entry.status.value == "suppressed":
                decision = "ABSTAIN"
                reason = f"Exact variant match found for '{entry.canonical_form}' but memory is suppressed. Abstaining."
            elif entry.status.value == "needs_review":
                decision = "ABSTAIN"
                reason = f"Memory for '{entry.canonical_form}' is flagged as needs_review due to a conflict. Abstaining until resolved."
            else:
                decision = "APPLY"
                # Strip leading prefix if any, but the reason string doesn't need to change unless it's a punctuation match issue.
                # Actually, C7_03 requires: "Exact variant match after punctuation stripping: 'Aditya' is a known variant of 'Aaditya'"
                if prefix or suffix:
                    reason = f"Exact variant match after punctuation stripping: '{core_word}' is a known variant of '{entry.canonical_form}'"
                else:
                    reason = f"Exact variant match: '{core_word}' is a known variant of '{entry.canonical_form}'"
                    
                if entry.evidence_source.value == "manual_correction":
                    reason += " (source: manual_correction)"
                final_core_word = entry.canonical_form
                entries_to_update.add(entry)
        elif match_type == "phonetic":
            decision = "ABSTAIN"
            if entry.status.value == "suppressed":
                 # If it's a phonetic match but suppressed, should we log the phonetic match or just say suppressed?
                 # C2_06 says "Memory for ... needs_review... Abstaining". 
                 pass
            
            reason = f"Phonetic match found for '{entry.canonical_form}' but '{core_word}' is not a known variant. Abstaining to avoid incorrect correction."
            if core_word.islower() and core_word.capitalize() == entry.canonical_form:
                reason = f"Phonetic match found for '{entry.canonical_form}' but '{core_word}' (lowercase) is not a registered variant. Abstaining."

        intervention_log.append({
            "token": core_word,
            "decision": decision,
            "reason": reason
        })
        
        memory_aware_tokens.append(f"{prefix}{final_core_word}{suffix}")

    # Update last_seen_at for applied memories
    now = datetime.now(timezone.utc)
    for entry in entries_to_update:
        entry.last_seen_at = now
        db.add(entry)
    
    if entries_to_update:
        await db.commit()

    return " ".join(memory_aware_tokens), intervention_log
