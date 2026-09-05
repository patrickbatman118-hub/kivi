import uuid

from app.config import settings

async def get_current_user_id() -> uuid.UUID:
    return uuid.UUID(settings.user_id)
