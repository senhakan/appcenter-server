from functools import lru_cache
from typing import Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AppCenter Server"
    app_version: str = "1.1.5"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+psycopg2://appcenter:Appcenter2026@127.0.0.1:5432/appcenter"

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

    # Remote support
    remote_support_enabled: bool = False
    remote_support_approval_timeout_sec: int = 30
    remote_support_default_max_duration_min: int = 60
    remote_support_max_duration_min: int = 480
    remote_support_vnc_password: str = ""
    guac_reverse_vnc_host: str = ""
    guac_reverse_vnc_port: int = 5500
    novnc_token_file: str = "/opt/appcenter/novnc/tokens.txt"
    novnc_ws_path: str = "/novnc-ws"
    remote_support_novnc_mode: str = "iframe"
    remote_support_ws_mode: str = "external"

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

    @field_validator("remote_support_novnc_mode", mode="before")
    @classmethod
    def validate_remote_support_novnc_mode(cls, value: str) -> str:
        mode = (value or "iframe").strip().lower()
        if mode not in {"iframe", "embedded"}:
            return "iframe"
        return mode

    @field_validator("remote_support_ws_mode", mode="before")
    @classmethod
    def validate_remote_support_ws_mode(cls, value: str) -> str:
        mode = (value or "external").strip().lower()
        if mode not in {"external", "internal"}:
            return "external"
        return mode


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
