"""Runtime settings, read from environment variables and an optional .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Hold application settings. Defaults suit local development; any field can be overridden."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://billing:billing@localhost:5432/billing"
    API_KEY: str = "dev-key"
    WEBHOOK_URL: str = "http://localhost:8000/api/v1/webhook-receiver"
    FUTURE_TOLERANCE_SECONDS: int = 300
    MAX_BATCH_SIZE: int = 1000
    NOTIFIER_POLL_SECONDS: float = 2.0
    NOTIFIER_MAX_ATTEMPTS: int = 8
    THRESHOLDS: tuple[int, ...] = (50, 80, 100)


settings = Settings()
