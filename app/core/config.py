from pydantic import ConfigDict
from pydantic_settings import BaseSettings
from typing import Optional, List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "PainSync API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    # AI Service (Claude API - per Main Prompt.txt)
    CLAUDE_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-5-haiku-20241022"
    
    # Legacy OpenAI-compatible support (optional fallback)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    AI_MODEL: str = "gpt-4.1-mini"  # fallback if Claude not configured

    # CORS (for Flutter mobile app)
    CORS_ORIGINS: List[str] = ["http://localhost", "http://127.0.0.1", "http://10.0.2.2"]

    # Pydantic v2 config
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"  # ← Allows undefined env vars without error
    )


settings = Settings()