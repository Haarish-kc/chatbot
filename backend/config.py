from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Inventory AI Assistant"
    ENVIRONMENT: Literal["development", "testing", "production"] = "development"
    DEBUG: bool = False

    # Inventory API
    INVENTORY_API_BASE_URL: str = "https://api.inventory.indianrailwayads.com/api"
    INVENTORY_ACCESS_TOKEN: str = ""
    INVENTORY_API_TIMEOUT: float = 30.0

    # LLM
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    LLM_API_KEY: str = "" # Optional generic fallback

    # Authentication
    JWT_SECRET_KEY: str = "" # Set to empty by default (no hardcoding). Loaded from .env.
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Chatbot
    CHAT_MAX_HISTORY: int = 20
    CHATBOT_NAME: str = "Inventory AI Assistant"

    # Security
    ALLOW_DEBUG_LOGGING: bool = False

    # SMTP Configuration
    EMAIL_HOST: str = "smtp.gmail.com"
    EMAIL_PORT: int = 587
    EMAIL_USER: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_FROM: str = ""
    EMAIL_SECURE: bool = False
    EMAIL_PROFILES: str = "ninjacorp"
    EMAIL_DEFAULT_PROFILE: str = ""
    IT_MANAGER_EMAIL: str = "it-manager@company.com"
    REPORT_RECIPIENT_EMAIL: str = "recipient@ninjacorp.in"
    VITE_WHATSAPP_SUPPORT_NUMBER: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()
