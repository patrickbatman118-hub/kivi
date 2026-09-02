from fastapi import FastAPI

app = FastAPI(
    title="Kivi",
    description="Memory-aware transcription corrector",
    version="1.0.0"
)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
