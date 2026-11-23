"""Validated runtime configuration; secrets are never embedded in settings."""
from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str = "development"
    metadata_database_url: str | None = None
    log_level: str = "INFO"
    statement_timeout_ms: int = 0
    connect_timeout_seconds: int = 10

    @classmethod
    def from_env(cls) -> "Settings":
        timeout = int(os.getenv("SNOWBRIDGE_STATEMENT_TIMEOUT_MS", "0"))
        connect_timeout = int(os.getenv("SNOWBRIDGE_CONNECT_TIMEOUT_SECONDS", "10"))
        if timeout < 0 or connect_timeout <= 0:
            raise ValueError("timeouts must be non-negative; connect timeout must be positive")
        return cls(
            environment=os.getenv("SNOWBRIDGE_ENV", "development"),
            metadata_database_url=os.getenv("SNOWBRIDGE_METADATA_DATABASE_URL"),
            log_level=os.getenv("SNOWBRIDGE_LOG_LEVEL", "INFO"),
            statement_timeout_ms=timeout,
            connect_timeout_seconds=connect_timeout,
        )
