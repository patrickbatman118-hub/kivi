import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user_id
from app.models.vocabulary import (
    User,
    VocabularyEntry,
    VocabularyVariant,
    EvidenceLog,
    StatusEnum,
    EvidenceSourceEnum,
    ConfidenceEnum,
    VariantSourceEnum,
    TriggerTypeEnum,
)
from app.schemas.vocabulary import MemoryCreate, MemoryResponse, MemoryStatusUpdate
from app.services.phonetic import get_phonetic_hash

router = APIRouter(prefix="/memory", tags=["memory"])

@router.get("", response_model=List[MemoryResponse])
async def list_memories(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id)
):
    stmt = select(VocabularyEntry).where(
        VocabularyEntry.user_id == user_id
    ).options(
        selectinload(VocabularyEntry.variants)
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()
    return entries

@router.post("", response_model=MemoryResponse)
async def add_memory(
    request: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id)
):
    # Make sure user exists
    user = await db.get(User, user_id)
    if not user:
        user = User(id=user_id)
        db.add(user)
        await db.commit()

    p_hash = get_phonetic_hash(request.canonical_form)
    
    # Conflict detection
    stmt = select(VocabularyEntry).where(
        VocabularyEntry.user_id == user_id,
        VocabularyEntry.phonetic_hash == p_hash
    )
    result = await db.execute(stmt)
    existing_entry = result.scalars().first()

    entry_status = StatusEnum.active
    if existing_entry and existing_entry.canonical_form.lower() != request.canonical_form.lower():
        entry_status = StatusEnum.needs_review

    new_entry = VocabularyEntry(
        user_id=user_id,
        canonical_form=request.canonical_form,
        category=request.category,
        status=entry_status,
        evidence_source=EvidenceSourceEnum.explicit_input,
        confidence=ConfidenceEnum.high,
        phonetic_hash=p_hash
    )
    db.add(new_entry)
    await db.flush()

    for var_text in request.variants:
        variant = VocabularyVariant(
            entry_id=new_entry.id,
            variant_text=var_text,
            source=VariantSourceEnum.user_provided
        )
        db.add(variant)

    evidence = EvidenceLog(
        entry_id=new_entry.id,
        trigger_type=TriggerTypeEnum.explicit_input
    )
    db.add(evidence)

    await db.commit()
    
    # Retrieve with variants to return
    stmt = select(VocabularyEntry).where(VocabularyEntry.id == new_entry.id).options(selectinload(VocabularyEntry.variants))
    res = await db.execute(stmt)
    
    if entry_status == StatusEnum.needs_review:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=409,
            content={
                "status": "conflict",
                "message": "Phonetic hash collision detected with existing entry. Entry created with status needs_review.",
                "conflicting_entry_id": str(existing_entry.id),
                "entry": {
                    "id": str(new_entry.id),
                    "canonical_form": new_entry.canonical_form,
                    "status": new_entry.status.value,
                }
            }
        )
        
    return res.scalars().first()

@router.patch("/{entry_id}", response_model=MemoryResponse)
async def update_memory_status(
    entry_id: uuid.UUID,
    request: MemoryStatusUpdate,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id)
):
    stmt = select(VocabularyEntry).where(
        VocabularyEntry.id == entry_id,
        VocabularyEntry.user_id == user_id
    ).options(selectinload(VocabularyEntry.variants))
    result = await db.execute(stmt)
    entry = result.scalars().first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
        
    entry.status = request.status
    await db.commit()
    await db.refresh(entry)
    return entry

@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id)
):
    stmt = select(VocabularyEntry).where(
        VocabularyEntry.id == entry_id,
        VocabularyEntry.user_id == user_id
    )
    result = await db.execute(stmt)
    entry = result.scalars().first()
    
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
        
    await db.delete(entry)
    await db.commit()
    return None

@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_memory(
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id)
):
    stmt = select(VocabularyEntry).where(VocabularyEntry.user_id == user_id)
    result = await db.execute(stmt)
    entries = result.scalars().all()
    
    for entry in entries:
        await db.delete(entry)
    
    await db.commit()
    return None
