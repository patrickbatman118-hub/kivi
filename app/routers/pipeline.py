import uuid
from fastapi import APIRouter, Depends, HTTPException
from google.genai import errors as genai_errors
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
    try:
        output, log = await process_transcript(
            db,
            user_id,
            request.asr_output,
            request.formatted_output
        )
    except genai_errors.APIError as e:
        # Surface the real Gemini status/message instead of letting it fall
        # through to a generic 500 "Internal Server Error" — a Gemini outage
        # is not a Kivi bug, and the response should say so.
        raise HTTPException(
            status_code=e.code,
            detail=f"Gemini API error ({e.code} {e.status}): {e.message}"
        )

    return ProcessResponse(
        memory_aware_output=output,
        intervention_log=log
    )
