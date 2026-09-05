from sqlalchemy import Column, String, Enum, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.database import Base

class CategoryEnum(str, enum.Enum):
    person_name = "person_name"
    org_name = "org_name"
    project_name = "project_name"
    product_name = "product_name"
    technical_term = "technical_term"
    acronym = "acronym"
    custom_spelling = "custom_spelling"

class StatusEnum(str, enum.Enum):
    active = "active"
    suppressed = "suppressed"
    deleted = "deleted"
    needs_review = "needs_review"

class EvidenceSourceEnum(str, enum.Enum):
    explicit_input = "explicit_input"
    manual_correction = "manual_correction"

class ConfidenceEnum(str, enum.Enum):
    high = "high"
    medium = "medium"

class VariantSourceEnum(str, enum.Enum):
    asr_error = "asr_error"
    user_provided = "user_provided"

class TriggerTypeEnum(str, enum.Enum):
    explicit_input = "explicit_input"
    manual_correction = "manual_correction"

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    entries = relationship("VocabularyEntry", back_populates="user")


class VocabularyEntry(Base):
    __tablename__ = "vocabulary_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    canonical_form = Column(String, nullable=False)
    category = Column(Enum(CategoryEnum), nullable=False)
    status = Column(Enum(StatusEnum), nullable=False)
    evidence_source = Column(Enum(EvidenceSourceEnum), nullable=False)
    confidence = Column(Enum(ConfidenceEnum), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Updated explicitly in app/services/pipeline.py on each APPLY — onupdate=func.now()
    # would not fire here since updates go through the async ORM, not raw SQL.
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    phonetic_hash = Column(String, nullable=True)

    user = relationship("User", back_populates="entries")
    variants = relationship("VocabularyVariant", back_populates="entry", cascade="all, delete-orphan")
    evidence_logs = relationship("EvidenceLog", back_populates="entry", cascade="all, delete-orphan")


class VocabularyVariant(Base):
    __tablename__ = "vocabulary_variants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id = Column(UUID(as_uuid=True), ForeignKey("vocabulary_entries.id", ondelete="CASCADE"), nullable=False)
    variant_text = Column(String, nullable=False)
    source = Column(Enum(VariantSourceEnum), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entry = relationship("VocabularyEntry", back_populates="variants")


class EvidenceLog(Base):
    __tablename__ = "evidence_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id = Column(UUID(as_uuid=True), ForeignKey("vocabulary_entries.id", ondelete="CASCADE"), nullable=False)
    trigger_type = Column(Enum(TriggerTypeEnum), nullable=False)
    asr_text = Column(String, nullable=True)
    corrected_text = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    entry = relationship("VocabularyEntry", back_populates="evidence_logs")
