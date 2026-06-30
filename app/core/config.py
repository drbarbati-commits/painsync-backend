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
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 20160  # 14 days

    # AI Service (Groq — free, OpenAI-compatible, Llama 3)
    GROQ_API_KEY: Optional[str] = None
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Gemini Vision API (for food / video analysis)
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Sentry
    SENTRY_DSN: Optional[str] = None

    # CORS (for Flutter mobile app)
    # Set CORS_ORIGINS env var as a JSON array, e.g.: '["https://example.com"]'
    # Use ["*"] to allow all origins (default for mobile/dev)
    CORS_ORIGINS: List[str] = ["*"]

    # Pydantic v2 config
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"  # ← Allows undefined env vars without error
    )


settings = Settings()