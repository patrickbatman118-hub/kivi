import uuid
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user_id
from app.services.correction import process_correction
from app.schemas.vocabulary import MemoryResponse

router = APIRouter(tags=["correction"])

class CorrectionRequest(BaseModel):
    original_formatted: str
    corrected_text: str

@router.post("/correct", response_model=List[MemoryResponse])
async def correct_endpoint(
    request: CorrectionRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id)
):
    return await process_correction(
        db,
        user_id,
        request.original_formatted,
        request.corrected_text
    )
