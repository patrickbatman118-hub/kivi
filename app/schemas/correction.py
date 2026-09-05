from pydantic import BaseModel

class CorrectionRequest(BaseModel):
    original_formatted: str
    corrected_text: str
