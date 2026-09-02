import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.vocabulary import VocabularyEntry, StatusEnum
from app.services.phonetic import get_phonetic_hash

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

    token_lower = token.lower()
    
    # Stage 1: Exact variant match (case-sensitive as per C2_05 notes: 'kiwi' lowercase should not trigger 'Kiwi')
    # Wait, the spec for C2_05 says: "The variant registered is 'Kiwi' (capitalised). 'kiwi' lowercase should not trigger."
    # So variant matching is CASE-SENSITIVE for exact variant match.
    # What about canonical form matching? The spec says "token exactly matches a known variant".
    for entry in user_memories:
        if entry.canonical_form == token:
             return entry, "canonical"
             
        for variant in entry.variants:
            if variant.variant_text == token:
                return entry, "exact_variant"

    # Stage 2: Phonetic hash match
    p_hash = get_phonetic_hash(token)
    if p_hash:
        for entry in user_memories:
            if entry.phonetic_hash == p_hash:
                return entry, "phonetic"

    return None, "none"
