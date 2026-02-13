from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from app.database import SessionLocal
from app.models import Agent, Setting

scheduler = AsyncIOScheduler(timezone="UTC")


def _get_setting(db, key: str, default: str) -> str:
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def check_offline_agents() -> None:
    db = SessionLocal()
    try:
        timeout_sec = int(_get_setting(db, "agent_timeout_sec", "300"))
        threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout_sec)
        agents = db.query(Agent).filter(Agent.last_seen < threshold, Agent.status == "online").all()
        for agent in agents:
            agent.status = "offline"
            db.add(agent)
        db.commit()
    finally:
        db.close()


def cleanup_old_logs() -> None:
    db = SessionLocal()
    try:
        retention_days = int(_get_setting(db, "log_retention_days", "30"))
        db.execute(
            text("DELETE FROM task_history WHERE created_at < datetime('now', :days)"),
            {"days": f"-{retention_days} days"},
        )
        db.commit()
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(check_offline_agents, "interval", minutes=2, id="offline_check", replace_existing=True)
    scheduler.add_job(cleanup_old_logs, "cron", hour=3, minute=0, id="log_cleanup", replace_existing=True)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

