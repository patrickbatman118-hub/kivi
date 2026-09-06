from google import genai

from app.config import settings

FORMATTER_PROMPT = """You are a transcript formatter. Convert this raw ASR output into \
clean, properly capitalised and punctuated text. Do not change any \
words or their meaning. Do not add or remove information. Return \
only the formatted text with no explanation.

ASR output: {asr_output}"""


async def generate_formatted_output(asr_output: str) -> str:
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=FORMATTER_PROMPT.format(asr_output=asr_output)
    )
    return response.text.strip()
