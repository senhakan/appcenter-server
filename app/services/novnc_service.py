from __future__ import annotations

import fcntl
import secrets
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings

settings = get_settings()


def _token_file_path() -> Path:
    return Path(settings.novnc_token_file).expanduser()


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def build_ticket(agent_ip: str, vnc_port: int = 5900) -> tuple[str, str]:
    """
    Create a one-time token mapping for websockify TokenFile plugin.
    Returns (token, ws_path).
    """
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


def cleanup_old_tokens(max_age_hours: int = 12, max_lines: int = 5000) -> None:
    """
    Best-effort compaction to keep token file from unbounded growth.
    TokenFile format has no expiry metadata, so we retain latest N lines.
    """
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
