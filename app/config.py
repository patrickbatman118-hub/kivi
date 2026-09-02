from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    db_url: str
    gemini_api_key: str
    user_id: str

    class Config:
        env_file = ".env"

settings = Settings()
