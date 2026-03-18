"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://werewolf:werewolf@localhost:5432/werewolf"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    api_key_header: str = "X-API-Key"

    # Game defaults
    default_speech_timeout: int = 60
    default_action_timeout: int = 45
    default_vote_timeout: int = 30

    # Timeout checker interval (seconds)
    timeout_check_interval: float = 1.0

    # Reconnect window (seconds)
    reconnect_window: int = 120

    # Bot takeover when disconnected
    bot_takeover_enabled: bool = True

    # CORS
    cors_origins: list[str] = ["*"]

    # Logging
    log_level: str = "INFO"

    model_config = {"env_prefix": "WEREWOLF_", "env_file": ".env"}
