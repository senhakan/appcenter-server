from __future__ import annotations

import configparser
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    app_name: str = "AppCenter Server"
    app_version: str = "1.1.7"
    api_v1_prefix: str = "/api/v1"

    # Database
    database_url: str = "postgresql+psycopg2://appcenter:Appcenter2026@127.0.0.1:5432/appcenter"

    # JWT
    secret_key: str = "change-me-in-production-use-a-strong-random-key"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # File upload
    upload_dir: str = "/var/lib/appcenter/uploads"
    max_upload_size: int = 2 * 1024 * 1024 * 1024
    max_icon_size: int = 5 * 1024 * 1024

    # Server
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # Logging
    log_file: str = "/var/log/appcenter/server.log"
    log_level: str = "INFO"

    # Remote support infrastructure
    guac_reverse_vnc_host: str = ""
    guac_reverse_vnc_port: int = 5500
    novnc_token_file: str = "/opt/appcenter/novnc/tokens.txt"
    novnc_ws_path: str = "/novnc-ws"

    # LDAP bootstrap
    ldap_server_uri: str = ""
    ldap_use_ssl: bool = False
    ldap_start_tls: bool = False
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    ldap_user_base_dn: str = ""
    ldap_user_filter: str = "(sAMAccountName={username})"
    ldap_group_base_dn: str = ""
    ldap_group_filter: str = "(|(member={user_dn})(uniqueMember={user_dn})(memberUid={username}))"
    ldap_ca_cert_file: str = ""
    ldap_timeout_sec: int = 10

    # Diagnostics
    config_file: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            return items or ["*"]
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                except Exception:
                    parsed = None
                if isinstance(parsed, list):
                    items = [str(item).strip() for item in parsed if str(item).strip()]
                    return items or ["*"]
            parts = [item.strip() for item in value.split(",") if item.strip()]
            return parts or ["*"]
        return ["*"]


def _repo_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "server.ini"


def _candidate_config_paths() -> list[Path]:
    return [
        Path("/opt/appcenter/server/config/server.ini"),
        Path("/etc/appcenter/server.ini"),
        _repo_config_path(),
    ]


def _flatten_config(data: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for section in ("app", "database", "jwt", "uploads", "server", "logging", "remote_support", "ldap"):
        value = data.get(section)
        if isinstance(value, dict):
            flat.update(value)
    for key, value in data.items():
        if key not in {"app", "database", "jwt", "uploads", "server", "logging", "remote_support", "ldap"}:
            flat[key] = value
    return flat


def _load_config_file() -> tuple[dict[str, Any], Path]:
    for path in _candidate_config_paths():
        if not path.exists():
            continue
        parser = configparser.ConfigParser()
        with path.open("r", encoding="utf-8") as fp:
            parser.read_file(fp)
        data = {section: dict(parser.items(section)) for section in parser.sections()}
        return _flatten_config(data), path
    searched = ", ".join(str(path) for path in _candidate_config_paths())
    raise RuntimeError(f"AppCenter config file not found. Expected one of: {searched}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw, path = _load_config_file()
    raw["config_file"] = str(path)
    return Settings.model_validate(raw)
