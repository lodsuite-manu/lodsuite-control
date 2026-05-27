"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Telegram
    telegram_bot_token: str = Field(default="")
    telegram_admin_user_ids: str = Field(default="")

    # Anthropic
    anthropic_api_key: str = Field(default="")

    # Database
    database_url: str = Field(default="sqlite+aiosqlite:///./lodsuite.db")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379")

    # Paths
    jobs_dir: Path = Field(default=Path("./jobs"))
    library_dir: Path = Field(default=Path("./library"))
    characters_dir: Path = Field(default=Path("./characters"))

    # Character
    default_character: str = Field(default="markus_industrial")

    # Render Worker Auth
    render_api_token: Optional[str] = Field(default=None)

    # Feature Flags
    mock_render: bool = Field(default=True)
    mock_script: bool = Field(default=True)

    # API
    api_base_url: str = Field(default="http://localhost:8000")

    @property
    def admin_user_ids(self) -> list[int]:
        """Parse admin user IDs from comma-separated string."""
        if not self.telegram_admin_user_ids:
            return []
        return [int(uid.strip()) for uid in self.telegram_admin_user_ids.split(",") if uid.strip()]

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.characters_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
