from functools import lru_cache
from typing import Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AppCenter Server"
    app_version: str = "1.1.0"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "sqlite:////var/lib/appcenter/appcenter.db"

    # JWT
    secret_key: str = "change-me-in-production-use-a-strong-random-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # File upload
    upload_dir: str = "/var/lib/appcenter/uploads"
    max_upload_size: int = 2 * 1024 * 1024 * 1024  # 2GB
    max_icon_size: int = 5 * 1024 * 1024  # 5MB

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    debug: bool = False
    cors_origins: list[str] = ["*"]

    # Logging
    log_file: str = "/var/log/appcenter/server.log"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[str, list[str]]) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",") if item.strip()]
            return parts or ["*"]
        return ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
