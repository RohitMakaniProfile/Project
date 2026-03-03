from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/nexusapi"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-to-a-random-secret-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/auth/callback"

    # App
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def sync_database_url(self) -> str:
        """Return a synchronous database URL for Alembic."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
