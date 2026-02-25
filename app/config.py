"""Application configuration from environment."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment (and .env)."""

    model_config = SettingsConfigDict(
        env_prefix="LEDGER_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    db_path: str = "./data/ledger.db"
    api_key: str = "change-me-in-production"
    timezone: str = "Asia/Jakarta"
    dash_user: str = "admin"
    dash_pass: str = "change-me"
    secret_key: str = "ledger-secret-change-me"

    @property
    def db_url(self) -> str:
        path = Path(self.db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path.resolve()}"


settings = Settings()
