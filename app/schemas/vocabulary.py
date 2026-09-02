from pydantic import BaseModel, ConfigDict
from typing import List, Optional
import uuid
from datetime import datetime
from app.models.vocabulary import CategoryEnum, StatusEnum, EvidenceSourceEnum, ConfidenceEnum, VariantSourceEnum

class VocabularyVariantBase(BaseModel):
    variant_text: str

class VocabularyVariantCreate(VocabularyVariantBase):
    pass

class VocabularyVariantResponse(VocabularyVariantBase):
    id: uuid.UUID
    source: VariantSourceEnum
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class MemoryCreate(BaseModel):
    canonical_form: str
    category: CategoryEnum
    variants: List[str] = []

class MemoryStatusUpdate(BaseModel):
    status: StatusEnum

class MemoryResponse(BaseModel):
    id: uuid.UUID
    canonical_form: str
    category: CategoryEnum
    status: StatusEnum
    evidence_source: EvidenceSourceEnum
    confidence: ConfidenceEnum
    phonetic_hash: Optional[str] = None
    created_at: datetime
    last_seen_at: datetime
    variants: List[VocabularyVariantResponse] = []
    
    model_config = ConfigDict(from_attributes=True)
