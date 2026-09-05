import asyncio
import uuid
import sys
import os

# Add the parent directory to sys.path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.vocabulary import (
    User,
    VocabularyEntry,
    VocabularyVariant,
    CategoryEnum,
    StatusEnum,
    EvidenceSourceEnum,
    ConfidenceEnum,
    VariantSourceEnum,
)
from app.services.phonetic import get_phonetic_hash

# Use the default user_id from .env.example
DEFAULT_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")

async def seed_data():
    async with AsyncSessionLocal() as session:
        # Create test user if not exists
        user = await session.get(User, DEFAULT_USER_ID)
        if not user:
            user = User(id=DEFAULT_USER_ID)
            session.add(user)
            await session.commit()
            print(f"Created default user with ID: {DEFAULT_USER_ID}")
        else:
            print(f"User with ID {DEFAULT_USER_ID} already exists")

        # Seed memory entry 1: Aaditya -> Aditya
        await seed_entry(
            session,
            user_id=user.id,
            canonical_form="Aaditya",
            category=CategoryEnum.person_name,
            variant_text="Aditya",
        )

        # Seed memory entry 2: Kivi -> Kiwi
        await seed_entry(
            session,
            user_id=user.id,
            canonical_form="Kivi",
            category=CategoryEnum.product_name,
            variant_text="Kiwi",
        )

        print("Seed data inserted successfully.")


async def seed_entry(session, user_id, canonical_form, category, variant_text):
    existing = await session.scalar(
        select(VocabularyEntry).where(
            VocabularyEntry.user_id == user_id,
            VocabularyEntry.canonical_form == canonical_form,
        )
    )
    if existing:
        print(f"Entry for '{canonical_form}' already exists, skipping.")
        return

    entry = VocabularyEntry(
        user_id=user_id,
        canonical_form=canonical_form,
        category=category,
        status=StatusEnum.active,
        evidence_source=EvidenceSourceEnum.explicit_input,
        confidence=ConfidenceEnum.high,
        phonetic_hash=get_phonetic_hash(canonical_form),
    )
    session.add(entry)
    await session.flush()  # flush to get entry.id

    variant = VocabularyVariant(
        entry_id=entry.id,
        variant_text=variant_text,
        source=VariantSourceEnum.user_provided,
    )
    session.add(variant)
    await session.commit()

if __name__ == "__main__":
    asyncio.run(seed_data())
