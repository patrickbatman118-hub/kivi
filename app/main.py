from fastapi import FastAPI
from app.routers import memory, pipeline, correction

app = FastAPI(
    title="Kivi",
    description="Memory-aware transcription corrector",
    version="1.0.0"
)

app.include_router(memory.router)
app.include_router(pipeline.router)
app.include_router(correction.router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
