import asyncio
import uuid
import sys
import os

# Add the parent directory to sys.path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        entry1 = VocabularyEntry(
            user_id=user.id,
            canonical_form="Aaditya",
            category=CategoryEnum.person_name,
            status=StatusEnum.active,
            evidence_source=EvidenceSourceEnum.explicit_input,
            confidence=ConfidenceEnum.high,
            phonetic_hash="ATJT" # Double metaphone for Aaditya/Aditya
        )
        session.add(entry1)
        await session.flush() # flush to get entry1.id

        variant1 = VocabularyVariant(
            entry_id=entry1.id,
            variant_text="Aditya",
            source=VariantSourceEnum.user_provided
        )
        session.add(variant1)

        # Seed memory entry 2: Kivi -> Kiwi
        entry2 = VocabularyEntry(
            user_id=user.id,
            canonical_form="Kivi",
            category=CategoryEnum.product_name,
            status=StatusEnum.active,
            evidence_source=EvidenceSourceEnum.explicit_input,
            confidence=ConfidenceEnum.high,
            phonetic_hash="KF" # Double metaphone for Kivi
        )
        session.add(entry2)
        await session.flush()

        variant2 = VocabularyVariant(
            entry_id=entry2.id,
            variant_text="Kiwi",
            source=VariantSourceEnum.user_provided
        )
        session.add(variant2)

        await session.commit()
        print("Seed data inserted successfully.")

if __name__ == "__main__":
    asyncio.run(seed_data())
