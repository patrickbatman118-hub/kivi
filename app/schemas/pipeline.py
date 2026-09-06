from pydantic import BaseModel
from typing import List, Optional

class ProcessRequest(BaseModel):
    asr_output: str
    formatted_output: Optional[str] = None

class DecisionLog(BaseModel):
    token: str
    decision: str
    reason: str

class ProcessResponse(BaseModel):
    memory_aware_output: str
    intervention_log: List[DecisionLog]
