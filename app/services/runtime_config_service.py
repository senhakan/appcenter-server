from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Setting


REMOTE_SUPPORT_ENABLED_KEY = "remote_support_enabled"
REMOTE_SUPPORT_APPROVAL_TIMEOUT_KEY = "remote_support_approval_timeout_sec"
REMOTE_SUPPORT_DEFAULT_MAX_DURATION_KEY = "remote_support_default_max_duration_min"
REMOTE_SUPPORT_MAX_DURATION_KEY = "remote_support_max_duration_min"
REMOTE_SUPPORT_NOVNC_MODE_KEY = "remote_support_novnc_mode"
REMOTE_SUPPORT_WS_MODE_KEY = "remote_support_ws_mode"
REMOTE_SUPPORT_CONTROL_BAR_MODE_KEY = "remote_support_control_bar_mode"
REMOTE_SUPPORT_LOG_SCREEN_ENABLED_KEY = "remote_support_log_screen_enabled"


@dataclass(frozen=True)
class RemoteSupportRuntimeConfig:
    enabled: bool
    approval_timeout_sec: int
    default_max_duration_min: int
    max_duration_min: int
    novnc_mode: str
    ws_mode: str
    control_bar_mode: str
    log_screen_enabled: bool


def _setting_map(db: Session, keys: list[str]) -> dict[str, str]:
    rows = db.query(Setting).filter(Setting.key.in_(keys)).all()
    out = {row.key: (row.value or "") for row in rows}
    for key in keys:
        out.setdefault(key, "")
    return out


def get_str(db: Session, key: str, default: str) -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    if not row or row.value is None:
        return default
    return str(row.value)


def get_bool(db: Session, key: str, default: bool = False) -> bool:
    raw = get_str(db, key, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_int(db: Session, key: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(get_str(db, key, str(default)).strip())
    except Exception:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def get_remote_support_runtime(db: Session) -> RemoteSupportRuntimeConfig:
    values = _setting_map(
        db,
        [
            REMOTE_SUPPORT_ENABLED_KEY,
            REMOTE_SUPPORT_APPROVAL_TIMEOUT_KEY,
            REMOTE_SUPPORT_DEFAULT_MAX_DURATION_KEY,
            REMOTE_SUPPORT_MAX_DURATION_KEY,
            REMOTE_SUPPORT_NOVNC_MODE_KEY,
            REMOTE_SUPPORT_WS_MODE_KEY,
            REMOTE_SUPPORT_CONTROL_BAR_MODE_KEY,
            REMOTE_SUPPORT_LOG_SCREEN_ENABLED_KEY,
        ],
    )
    enabled = str(values[REMOTE_SUPPORT_ENABLED_KEY]).strip().lower() in {"1", "true", "yes", "on"}
    approval_timeout_sec = get_int(
        db,
        REMOTE_SUPPORT_APPROVAL_TIMEOUT_KEY,
        30,
        minimum=30,
        maximum=3600,
    )
    default_max_duration_min = get_int(
        db,
        REMOTE_SUPPORT_DEFAULT_MAX_DURATION_KEY,
        60,
        minimum=1,
        maximum=480,
    )
    max_duration_min = get_int(
        db,
        REMOTE_SUPPORT_MAX_DURATION_KEY,
        480,
        minimum=1,
        maximum=480,
    )
    if default_max_duration_min > max_duration_min:
        default_max_duration_min = max_duration_min
    novnc_mode = str(values[REMOTE_SUPPORT_NOVNC_MODE_KEY] or "iframe").strip().lower()
    if novnc_mode not in {"iframe", "embedded"}:
        novnc_mode = "iframe"
    ws_mode = str(values[REMOTE_SUPPORT_WS_MODE_KEY] or "external").strip().lower()
    if ws_mode not in {"external", "internal"}:
        ws_mode = "external"
    control_bar_mode = str(values[REMOTE_SUPPORT_CONTROL_BAR_MODE_KEY] or "embedded").strip().lower()
    if control_bar_mode not in {"embedded", "topbar"}:
        control_bar_mode = "embedded"
    log_screen_enabled = str(values[REMOTE_SUPPORT_LOG_SCREEN_ENABLED_KEY] or "true").strip().lower() in {"1", "true", "yes", "on"}
    return RemoteSupportRuntimeConfig(
        enabled=enabled,
        approval_timeout_sec=approval_timeout_sec,
        default_max_duration_min=default_max_duration_min,
        max_duration_min=max_duration_min,
        novnc_mode=novnc_mode,
        ws_mode=ws_mode,
        control_bar_mode=control_bar_mode,
        log_screen_enabled=log_screen_enabled,
    )


def is_remote_support_enabled(db: Session) -> bool:
    return get_remote_support_runtime(db).enabled
