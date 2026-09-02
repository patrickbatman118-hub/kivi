import uuid
import difflib
from typing import List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.vocabulary import (
    VocabularyEntry, 
    VocabularyVariant, 
    EvidenceLog, 
    CategoryEnum,
    StatusEnum,
    EvidenceSourceEnum,
    ConfidenceEnum,
    VariantSourceEnum,
    TriggerTypeEnum
)
from app.services.phonetic import get_phonetic_hash
from app.services.pipeline import strip_punctuation

async def process_correction(
    db: AsyncSession,
    user_id: uuid.UUID,
    original_formatted: str,
    corrected_text: str,
    session_id: str = None
) -> List[VocabularyEntry]:
    
    orig_tokens = original_formatted.split()
    corr_tokens = corrected_text.split()
    
    matcher = difflib.SequenceMatcher(None, orig_tokens, corr_tokens)
    
    updated_entries = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            # Only handle 1-to-1 word replacements for now to avoid complex multi-word mappings
            if (i2 - i1) == 1 and (j2 - j1) == 1:
                orig_raw = orig_tokens[i1]
                corr_raw = corr_tokens[j1]
                
                _, orig_core, _ = strip_punctuation(orig_raw)
                _, corr_core, _ = strip_punctuation(corr_raw)
                
                if not orig_core or not corr_core or orig_core == corr_core:
                    continue
                    
                # We have a replacement: orig_core -> corr_core
                entry = await apply_learning(db, user_id, orig_core, corr_core, original_formatted, corrected_text, session_id)
                updated_entries.append(entry)
                
    return updated_entries

async def apply_learning(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    orig_core: str, 
    corr_core: str,
    full_orig: str,
    full_corr: str,
    session_id: str
) -> VocabularyEntry:
    # Check if a memory already exists for the corrected form
    stmt = select(VocabularyEntry).where(
        VocabularyEntry.user_id == user_id,
        VocabularyEntry.canonical_form == corr_core
    ).options(selectinload(VocabularyEntry.variants))
    
    result = await db.execute(stmt)
    entry = result.scalars().first()
    
    if entry:
        # Check if variant already exists
        variant_exists = any(v.variant_text == orig_core for v in entry.variants)
        if not variant_exists:
            new_variant = VocabularyVariant(
                entry_id=entry.id,
                variant_text=orig_core,
                source=VariantSourceEnum.user_provided
            )
            db.add(new_variant)
            entry.variants.append(new_variant)
    else:
        # Create new memory
        p_hash = get_phonetic_hash(corr_core)
        
        # Check for conflict
        conflict_stmt = select(VocabularyEntry).where(
            VocabularyEntry.user_id == user_id,
            VocabularyEntry.phonetic_hash == p_hash
        )
        conflict_result = await db.execute(conflict_stmt)
        existing = conflict_result.scalars().first()
        
        status = StatusEnum.needs_review if existing else StatusEnum.active
        
        # The spec requires a category. For auto-learning we might default to custom_spelling 
        # or person_name. Let's use custom_spelling as a safe default for unknown.
        entry = VocabularyEntry(
            user_id=user_id,
            canonical_form=corr_core,
            category=CategoryEnum.custom_spelling,
            status=status,
            evidence_source=EvidenceSourceEnum.manual_correction,
            confidence=ConfidenceEnum.high,
            phonetic_hash=p_hash
        )
        db.add(entry)
        await db.flush() # flush to get id
        
        new_variant = VocabularyVariant(
            entry_id=entry.id,
            variant_text=orig_core,
            source=VariantSourceEnum.user_provided
        )
        db.add(new_variant)
        
        # Have to wait to avoid DetachedInstanceError or similar, but adding to session is fine.
        entry.variants = [new_variant]
        
    evidence = EvidenceLog(
        entry_id=entry.id,
        trigger_type=TriggerTypeEnum.manual_correction,
        asr_text=None,
        corrected_text=full_corr,
        session_id=session_id
    )
    db.add(evidence)
    
    await db.commit()
    await db.refresh(entry)
    
    # Reload with variants correctly
    stmt_reload = select(VocabularyEntry).where(VocabularyEntry.id == entry.id).options(selectinload(VocabularyEntry.variants))
    res = await db.execute(stmt_reload)
    return res.scalars().first()
