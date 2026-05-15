from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[4]
API_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
SANDBOX_DIR = DATA_DIR / "sandbox"
AUDIO_DIR = DATA_DIR / "audio"


class Settings(BaseSettings):
    app_name: str = "Agent Core API"
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
            "http://8.133.162.213:8080",
        ]
    )
    dev_jwt_token: str = "agent-core-dev-token"
    default_model: str = "MiMo-V2.5-Pro"
    memory_window: int = 20
    max_iterations: int = 10
    mimo_base_url: str | None = None
    mimo_api_key: str | None = None
    mimo_timeout_seconds: float = 30.0
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "AGENT_CORE_DATABASE_URL"),
    )
    redis_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices("REDIS_HOST", "AGENT_CORE_REDIS_HOST"),
    )
    redis_port: int = Field(
        default=6379,
        validation_alias=AliasChoices("REDIS_PORT", "AGENT_CORE_REDIS_PORT"),
    )
    redis_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("REDIS_PASSWORD", "AGENT_CORE_REDIS_PASSWORD"),
    )
    redis_db: int = Field(
        default=0,
        validation_alias=AliasChoices("REDIS_DB", "AGENT_CORE_REDIS_DB"),
    )
    mimo_fallback: list[str] = Field(
        default_factory=lambda: ["MiMo-V2.5-Pro", "MiMo-V2.5", "MiMo-V2-Pro"]
    )

    model_config = SettingsConfigDict(
        env_prefix="AGENT_CORE_",
        env_file=API_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

for directory in (DATA_DIR, SANDBOX_DIR, AUDIO_DIR):
    directory.mkdir(parents=True, exist_ok=True)