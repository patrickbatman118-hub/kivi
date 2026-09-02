import uuid
from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.database import get_db
from app.routers.memory import get_current_user_id
from app.services.pipeline import process_transcript

router = APIRouter(prefix="/process", tags=["pipeline"])

class ProcessRequest(BaseModel):
    asr_output: str
    formatted_output: str

class DecisionLog(BaseModel):
    token: str
    decision: str
    reason: str

class ProcessResponse(BaseModel):
    memory_aware_output: str
    intervention_log: List[DecisionLog]

@router.post("", response_model=ProcessResponse)
async def process_endpoint(
    request: ProcessRequest,
    db: AsyncSession = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id)
):
    output, log = await process_transcript(
        db, 
        user_id, 
        request.asr_output, 
        request.formatted_output
    )
    
    return ProcessResponse(
        memory_aware_output=output,
        intervention_log=log
    )
