from pydantic_settings import BaseSettings
from typing import Optional, Dict, Any, List
import os
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    PROJECT_NAME: str = "LostPets API"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "API for finding lost pets using computer vision"
    API_V1_STR: str = "/api/v1"

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "secret_key")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    # Database - Railway предоставляет DATABASE_URL автоматически
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/lostpets_db")
    DATABASE_URL_LOCAL: str = os.getenv("DATABASE_URL_LOCAL", "postgresql://postgres:postgres@localhost:5432/lostpets_db")

    # AWS
    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_BUCKET_NAME: str = os.getenv("AWS_BUCKET_NAME", "lostpets-images")

    # Similarity threshold for pet matching
    SIMILARITY_THRESHOLD: float = 0.35

    # Email verification settings
    VERIFICATION_CODE_EXPIRE_MINUTES: int = 15
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "noreply@lostpets.com")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()