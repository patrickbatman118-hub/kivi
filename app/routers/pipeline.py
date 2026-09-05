import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user_id
from app.services.pipeline import process_transcript
from app.schemas.pipeline import ProcessRequest, ProcessResponse

router = APIRouter(prefix="/process", tags=["pipeline"])

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
