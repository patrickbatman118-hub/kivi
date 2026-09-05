import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.vocabulary import VocabularyEntry, StatusEnum
from app.services.phonetic import get_phonetic_hashes

async def load_user_memory(db: AsyncSession, user_id: uuid.UUID) -> List[VocabularyEntry]:
    """Loads all memories for a user."""
    stmt = select(VocabularyEntry).where(
        VocabularyEntry.user_id == user_id
    ).options(selectinload(VocabularyEntry.variants))
    result = await db.execute(stmt)
    return result.scalars().all()

def retrieve_memory_for_token(
    token: str, 
    user_memories: List[VocabularyEntry]
) -> Tuple[Optional[VocabularyEntry], str]:
    """
    Two-stage retrieval for a single token.
    Returns (MemoryEntry or None, MatchType: 'exact_variant' | 'phonetic' | 'none')
    """
    if not token:
        return None, "none"

    # Stage 1: exact match, case-sensitive (a lowercase 'kiwi' must not match a
    # registered variant 'Kiwi' — see C2_05 in evaluation/cases.json).
    for entry in user_memories:
        if entry.canonical_form == token:
             return entry, "canonical"
             
        for variant in entry.variants:
            if variant.variant_text == token:
                return entry, "exact_variant"

    # Stage 2: Phonetic hash match
    # Check both Double Metaphone codes of the incoming token against each
    # entry's stored primary code (only the primary code is stored on write).
    primary, secondary = get_phonetic_hashes(token)
    token_codes = {c for c in (primary, secondary) if c}
    if token_codes:
        for entry in user_memories:
            if entry.phonetic_hash and entry.phonetic_hash in token_codes:
                return entry, "phonetic"

    return None, "none"
