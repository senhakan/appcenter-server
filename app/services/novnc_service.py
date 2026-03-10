from __future__ import annotations

import threading
import fcntl
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.services import runtime_config_service as runtime_config

settings = get_settings()
_INTERNAL_TICKET_TTL_SEC = 120
_internal_tickets: dict[str, tuple[str, int, float]] = {}
_internal_lock = threading.Lock()


def _token_file_path() -> Path:
    return Path(settings.novnc_token_file).expanduser()


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _cleanup_internal_tickets(now_monotonic: float) -> None:
    expired = [k for k, (_, _, exp) in _internal_tickets.items() if exp <= now_monotonic]
    for k in expired:
        _internal_tickets.pop(k, None)


def _build_internal_ticket(agent_ip: str, vnc_port: int) -> tuple[str, str]:
    token = f"rs-{secrets.token_urlsafe(18)}"
    expires_at = time.monotonic() + _INTERNAL_TICKET_TTL_SEC
    with _internal_lock:
        _cleanup_internal_tickets(time.monotonic())
        _internal_tickets[token] = (agent_ip, vnc_port, expires_at)
    return token, settings.novnc_ws_path


def _build_external_ticket(agent_ip: str, vnc_port: int) -> tuple[str, str]:
    token = f"rs-{secrets.token_urlsafe(18)}"
    mapping = f"{token}: {agent_ip}:{vnc_port}\n"

    token_file = _token_file_path()
    _ensure_parent_dir(token_file)
    token_file.touch(exist_ok=True)

    with token_file.open("a+", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(mapping)
        f.flush()
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return token, settings.novnc_ws_path


def build_ticket(agent_ip: str, vnc_port: int = 5900) -> tuple[str, str]:
    """
    Create a one-time ticket for remote support WebSocket bridge.
    Returns (token, ws_path).
    """
    db = SessionLocal()
    try:
        runtime = runtime_config.get_remote_support_runtime(db)
    finally:
        db.close()
    if runtime.ws_mode == "internal":
        return _build_internal_ticket(agent_ip, vnc_port)
    return _build_external_ticket(agent_ip, vnc_port)


def consume_internal_ticket(token: str) -> tuple[str, int] | None:
    """
    Consume one-time in-memory ticket for internal WS bridge mode.
    Returns (agent_ip, vnc_port) if valid, else None.
    """
    if not token:
        return None
    now = time.monotonic()
    with _internal_lock:
        _cleanup_internal_tickets(now)
        entry = _internal_tickets.pop(token, None)
    if not entry:
        return None
    agent_ip, vnc_port, expires_at = entry
    if expires_at <= now:
        return None
    return agent_ip, vnc_port


def cleanup_old_tokens(max_age_hours: int = 12, max_lines: int = 5000) -> None:
    """
    Best-effort compaction to keep token file from unbounded growth.
    TokenFile format has no expiry metadata, so we retain latest N lines.
    """
    db = SessionLocal()
    try:
        runtime = runtime_config.get_remote_support_runtime(db)
    finally:
        db.close()
    if runtime.ws_mode == "internal":
        with _internal_lock:
            _cleanup_internal_tickets(time.monotonic())
        return

    token_file = _token_file_path()
    if not token_file.exists():
        return
    try:
        lines = token_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) <= max_lines:
        return
    keep = lines[-max_lines:]
    try:
        token_file.write_text("\n".join(keep) + "\n", encoding="utf-8")
    except OSError:
        return


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
