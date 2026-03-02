from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import Agent, RemoteSupportRecording, RemoteSupportSession, Setting

settings = get_settings()

RECORDING_SETTING_KEY = "session_recording_enabled"
RECORDING_FPS_SETTING_KEY = "session_recording_fps"
MIN_RECORDING_FPS = 1
MAX_RECORDING_FPS = 30
DEFAULT_RECORDING_FPS = 10


@dataclass
class _RuntimeRecording:
    session_id: int
    recording_id: int
    process: subprocess.Popen
    output_path: str
    log_path: str
    stop_requested: bool = False


_RUNTIME_LOCK = threading.Lock()
_RUNTIME_BY_SESSION: dict[int, _RuntimeRecording] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_bool(value: str, default: bool = False) -> bool:
    raw = (value or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _get_setting(db: Session, key: str, default: str) -> str:
    item = db.query(Setting).filter(Setting.key == key).first()
    return item.value if item else default


def is_recording_enabled(db: Session) -> bool:
    return _parse_bool(_get_setting(db, RECORDING_SETTING_KEY, "false"), default=False)


def get_recording_fps(db: Session) -> int:
    raw = _get_setting(db, RECORDING_FPS_SETTING_KEY, str(DEFAULT_RECORDING_FPS))
    try:
        fps = int((raw or "").strip())
    except Exception:
        return DEFAULT_RECORDING_FPS
    return min(MAX_RECORDING_FPS, max(MIN_RECORDING_FPS, fps))


def get_recordings_root() -> Path:
    root = Path(settings.upload_dir).expanduser().resolve() / "recordings"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _dependency_status() -> dict[str, object]:
    missing: list[str] = []
    if not shutil.which("gst-launch-1.0"):
        missing.append("gst-launch-1.0")
    checks = {
        "rfbsrc": "rfbsrc",
        "x264enc": "x264enc",
        "mp4mux": "mp4mux",
    }
    for binary, plugin in checks.items():
        if shutil.which("gst-inspect-1.0") is None:
            missing.append("gst-inspect-1.0")
            break
        rc = subprocess.run(
            ["gst-inspect-1.0", plugin],
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        if rc != 0:
            missing.append(f"plugin:{plugin}")
    return {"ok": len(missing) == 0, "missing": missing}


def get_service_status(db: Session) -> dict[str, object]:
    dep = _dependency_status()
    enabled = is_recording_enabled(db)
    target_fps = get_recording_fps(db)
    with _RUNTIME_LOCK:
        running = [{"session_id": r.session_id, "recording_id": r.recording_id} for r in _RUNTIME_BY_SESSION.values()]
    return {
        "enabled": enabled,
        "target_fps": target_fps,
        "deps_ok": bool(dep["ok"]),
        "missing": dep["missing"],
        "active": bool(enabled and dep["ok"]),
        "running": running,
    }


def ensure_service_ready(db: Session) -> None:
    if not is_recording_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session recording disabled. Enable it from Settings > Session Recording.",
        )
    dep = _dependency_status()
    if not dep["ok"]:
        missing = ", ".join(dep["missing"])
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Session recording service not ready. Missing dependencies: "
                f"{missing}. Install GStreamer packages and retry."
            ),
        )


def _ffprobe_duration_sec(file_path: str) -> Optional[int]:
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nk=1:nw=1",
                file_path,
            ],
            text=True,
        ).strip()
        if not out:
            return None
        return max(int(float(out)), 0)
    except Exception:
        return None


def _tail_log(log_path: str, max_chars: int = 1200) -> str:
    if not log_path or not os.path.exists(log_path):
        return ""
    try:
        with open(log_path, "rb") as fp:
            fp.seek(0, os.SEEK_END)
            size = fp.tell()
            fp.seek(max(size - max_chars, 0))
            raw = fp.read().decode("utf-8", errors="replace")
        return raw.strip()
    except Exception:
        return ""


def _watch_recording(runtime: _RuntimeRecording) -> None:
    exit_code = runtime.process.wait()
    ended_at = _utcnow()
    file_size = None
    if runtime.output_path and os.path.exists(runtime.output_path):
        try:
            file_size = os.path.getsize(runtime.output_path)
        except OSError:
            file_size = None

    duration_sec = _ffprobe_duration_sec(runtime.output_path)
    err_text = ""
    final_status = "failed"
    if runtime.stop_requested:
        final_status = "stopped" if file_size and file_size > 0 else "failed"
        if final_status == "failed":
            err_text = "Recording stopped but output file was not produced."
    elif exit_code == 0 and file_size and file_size > 0:
        final_status = "completed"
    else:
        err_text = f"gst-launch exit={exit_code}. {_tail_log(runtime.log_path)}".strip()

    db = SessionLocal()
    try:
        rec = db.query(RemoteSupportRecording).filter(RemoteSupportRecording.id == runtime.recording_id).first()
        if rec and rec.status == "recording":
            rec.status = final_status
            rec.ended_at = ended_at
            rec.duration_sec = duration_sec
            rec.file_size_bytes = file_size
            rec.error_message = err_text[:5000] if err_text else None
            db.add(rec)
            db.commit()
    finally:
        db.close()
        with _RUNTIME_LOCK:
            current = _RUNTIME_BY_SESSION.get(runtime.session_id)
            if current and current.recording_id == runtime.recording_id:
                _RUNTIME_BY_SESSION.pop(runtime.session_id, None)


def _mark_stale_recordings(db: Session, session_id: int) -> None:
    rows = (
        db.query(RemoteSupportRecording)
        .filter(RemoteSupportRecording.session_id == session_id, RemoteSupportRecording.status == "recording")
        .all()
    )
    if not rows:
        return
    now = _utcnow()
    for row in rows:
        row.status = "failed"
        row.ended_at = now
        row.error_message = "Stale recording entry recovered by startup."
        db.add(row)


def start_recording(db: Session, session_id: int, trigger_source: str = "manual") -> tuple[RemoteSupportRecording, bool]:
    ensure_service_ready(db)
    session = db.query(RemoteSupportSession).filter(RemoteSupportSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    state = (session.status or "").lower()
    if state not in {"approved", "connecting", "active"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Session not recordable in state: {session.status}")
    if not session.vnc_password:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Missing VNC password for recording")

    agent = db.query(Agent).filter(Agent.uuid == session.agent_uuid).first()
    agent_ip = (agent.ip_address or "").strip() if agent else ""
    if not agent_ip:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Missing agent IP for recording")

    with _RUNTIME_LOCK:
        runtime = _RUNTIME_BY_SESSION.get(session_id)
        if runtime and runtime.process.poll() is None:
            rec = db.query(RemoteSupportRecording).filter(RemoteSupportRecording.id == runtime.recording_id).first()
            if rec:
                return rec, False

    _mark_stale_recordings(db, session_id)

    root = get_recordings_root() / f"session_{session_id}"
    root.mkdir(parents=True, exist_ok=True)
    stamp = _utcnow().strftime("%Y%m%d_%H%M%S")
    target_fps = get_recording_fps(db)
    rec = RemoteSupportRecording(
        session_id=session.id,
        agent_uuid=session.agent_uuid,
        status="recording",
        target_fps=target_fps,
        trigger_source=(trigger_source or "manual")[:120],
        started_at=_utcnow(),
    )
    db.add(rec)
    db.flush()

    output_path = (root / f"recording_{rec.id}_{stamp}.mp4").resolve()
    log_path = (root / f"recording_{rec.id}_{stamp}.log").resolve()
    rec.file_path = str(output_path)
    rec.log_path = str(log_path)

    cmd = [
        "gst-launch-1.0",
        "-e",
        "rfbsrc",
        f"host={agent_ip}",
        "port=20010",
        f"password={session.vnc_password}",
        "shared=true",
        "view-only=true",
        "incremental=true",
        "use-copyrect=true",
        "do-timestamp=true",
        "!",
        "videoconvert",
        "!",
        "videorate",
        "!",
        f"video/x-raw,format=I420,framerate={target_fps}/1",
        "!",
        "x264enc",
        "tune=zerolatency",
        "speed-preset=veryfast",
        "bitrate=2500",
        "key-int-max=20",
        "!",
        "h264parse",
        "!",
        "mp4mux",
        "faststart=true",
        "!",
        "filesink",
        f"location={str(output_path)}",
    ]

    try:
        log_fp = open(log_path, "ab")
        process = subprocess.Popen(cmd, stdout=log_fp, stderr=subprocess.STDOUT)
        log_fp.close()
    except Exception as exc:
        rec.status = "failed"
        rec.ended_at = _utcnow()
        rec.error_message = f"Failed to start gst-launch: {exc}"
        db.add(rec)
        db.commit()
        db.refresh(rec)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to start recording process")

    runtime = _RuntimeRecording(
        session_id=session.id,
        recording_id=rec.id,
        process=process,
        output_path=str(output_path),
        log_path=str(log_path),
    )
    with _RUNTIME_LOCK:
        _RUNTIME_BY_SESSION[session.id] = runtime

    db.add(rec)
    db.commit()
    db.refresh(rec)

    watcher = threading.Thread(target=_watch_recording, args=(runtime,), daemon=True)
    watcher.start()
    return rec, True


def stop_recording(db: Session, session_id: int, reason: str = "manual_stop") -> bool:
    _ = reason
    stopped = False
    with _RUNTIME_LOCK:
        runtime = _RUNTIME_BY_SESSION.get(session_id)
        if runtime and runtime.process.poll() is None:
            runtime.stop_requested = True
            try:
                runtime.process.send_signal(signal.SIGINT)
                stopped = True
            except Exception:
                pass

    if stopped:
        return True

    rows = (
        db.query(RemoteSupportRecording)
        .filter(RemoteSupportRecording.session_id == session_id, RemoteSupportRecording.status == "recording")
        .all()
    )
    if not rows:
        return False
    now = _utcnow()
    for row in rows:
        row.status = "stopped"
        row.ended_at = now
        row.error_message = "Stopped without active runtime process."
        db.add(row)
    db.commit()
    return True
