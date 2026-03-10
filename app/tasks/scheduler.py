from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import get_settings
from app.database import SessionLocal
from app.models import Agent, AgentStatusHistory, SamReportSchedule, Setting, SoftwareChangeHistory, TaskHistory
from app.services.announcement_service import check_expired_deliveries, check_scheduled_announcements
from app.services import dynamic_group_service
from app.services import inventory_service
from app.services import remote_support_service
from app.services import runtime_config_service as runtime_config
from app.services.system_profile_service import cleanup_old_identity_history, cleanup_old_status_history, cleanup_old_system_history

scheduler: Optional[AsyncIOScheduler] = None
_last_dynamic_group_sync_at: Optional[datetime] = None
logger = logging.getLogger("appcenter.scheduler")


def _get_setting(db, key: str, default: str) -> str:
    setting = db.query(Setting).filter(Setting.key == key).first()
    return setting.value if setting else default


def check_offline_agents() -> None:
    db = SessionLocal()
    try:
        timeout_sec = int(_get_setting(db, "agent_timeout_sec", "300"))
        threshold = datetime.now(timezone.utc) - timedelta(seconds=timeout_sec)
        agents = db.query(Agent).filter(Agent.last_seen < threshold, Agent.status == "online").all()
        offline_ids: list[str] = []
        for agent in agents:
            db.add(
                AgentStatusHistory(
                    agent_uuid=agent.uuid,
                    detected_at=datetime.now(timezone.utc),
                    old_status=agent.status,
                    new_status="offline",
                    reason="timeout",
                )
            )
            agent.status = "offline"
            db.add(agent)
            offline_ids.append(agent.uuid)
        db.commit()
        if offline_ids:
            remote_support_service.end_sessions_for_offline_agents(db, offline_ids)
    finally:
        db.close()


def check_remote_support_timeouts() -> None:
    db = SessionLocal()
    try:
        if not runtime_config.is_remote_support_enabled(db):
            return
        remote_support_service.check_approval_timeouts(db)
        remote_support_service.check_max_durations(db)
    finally:
        db.close()


def cleanup_old_logs() -> None:
    db = SessionLocal()
    try:
        retention_days = int(_get_setting(db, "log_retention_days", "30"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        db.query(TaskHistory).filter(TaskHistory.created_at < cutoff).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def cleanup_old_inventory_history() -> None:
    db = SessionLocal()
    try:
        retention = int(_get_setting(db, "inventory_history_retention_days", "90"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        db.query(SoftwareChangeHistory).filter(SoftwareChangeHistory.detected_at < cutoff).delete()
        db.commit()
    finally:
        db.close()


def cleanup_old_system_history_job() -> None:
    db = SessionLocal()
    try:
        retention = int(_get_setting(db, "system_history_retention_days", "360"))
        cleanup_old_system_history(db, retention)
        cleanup_old_identity_history(db, retention)
        cleanup_old_status_history(db, retention)
    finally:
        db.close()


def sync_dynamic_groups_job() -> None:
    global _last_dynamic_group_sync_at
    db = SessionLocal()
    try:
        try:
            interval_sec = int(_get_setting(db, "dynamic_group_sync_interval_sec", "120"))
        except Exception:
            interval_sec = 120
        interval_sec = max(30, interval_sec)
        now = datetime.now(timezone.utc)
        if _last_dynamic_group_sync_at is not None:
            elapsed = (now - _last_dynamic_group_sync_at).total_seconds()
            if elapsed < interval_sec:
                return
        dynamic_group_service.apply_dynamic_groups_for_all_agents(db)
        db.commit()
        _last_dynamic_group_sync_at = now
    finally:
        db.close()


def run_due_sam_report_schedules() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = db.query(SamReportSchedule).filter(SamReportSchedule.is_active.is_(True)).all()
        settings = get_settings()
        report_dir = Path(settings.upload_dir) / "reports" / "sam"
        report_dir.mkdir(parents=True, exist_ok=True)

        for item in rows:
            try:
                if item.next_run_at is None:
                    item.next_run_at = inventory_service.compute_sam_schedule_following_run(item.cron_expr, now - timedelta(minutes=1))
                    db.add(item)
                    db.commit()
                    db.refresh(item)
                if item.next_run_at is None or item.next_run_at > now:
                    continue

                header, data_rows = inventory_service.build_sam_report_data(
                    db,
                    report_type=item.report_type,
                    platform="all",
                )
                stamp = now.strftime("%Y%m%d_%H%M%S")
                file_name = f"{item.report_type}_schedule_{item.id}_{stamp}.csv"
                file_path = report_dir / file_name
                with file_path.open("w", encoding="utf-8", newline="") as fp:
                    writer = csv.writer(fp)
                    writer.writerow(header)
                    for row in data_rows:
                        writer.writerow(row)

                item.last_run_at = now
                item.next_run_at = inventory_service.compute_sam_schedule_following_run(item.cron_expr, now)
                db.add(item)
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.exception("SAM schedule execution failed (id=%s): %s", item.id, exc)
    finally:
        db.close()


def check_scheduled_announcements_job() -> None:
    db = SessionLocal()
    try:
        check_scheduled_announcements(db)
    finally:
        db.close()


def check_expired_deliveries_job() -> None:
    db = SessionLocal()
    try:
        check_expired_deliveries(db)
    finally:
        db.close()


def start_scheduler() -> None:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler(timezone="UTC")

    if scheduler.running:
        return

    scheduler.add_job(check_offline_agents, "interval", minutes=2, id="offline_check", replace_existing=True)
    scheduler.add_job(cleanup_old_logs, "cron", hour=3, minute=0, id="log_cleanup", replace_existing=True)
    scheduler.add_job(cleanup_old_inventory_history, "cron", hour=3, minute=10, id="inventory_history_cleanup", replace_existing=True)
    scheduler.add_job(cleanup_old_system_history_job, "cron", hour=3, minute=20, id="system_history_cleanup", replace_existing=True)
    scheduler.add_job(check_remote_support_timeouts, "interval", seconds=30, id="rs_timeouts", replace_existing=True)
    scheduler.add_job(sync_dynamic_groups_job, "interval", seconds=15, id="dynamic_group_sync", replace_existing=True)
    scheduler.add_job(run_due_sam_report_schedules, "interval", seconds=30, id="sam_report_schedules", replace_existing=True)
    scheduler.add_job(
        check_scheduled_announcements_job,
        "interval",
        seconds=30,
        id="check_scheduled_announcements",
        replace_existing=True,
    )
    scheduler.add_job(
        check_expired_deliveries_job,
        "interval",
        seconds=60,
        id="check_expired_deliveries",
        replace_existing=True,
    )
    try:
        scheduler.start()
    except RuntimeError:
        # Test/worker lifecycles may close event loops between app startups.
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(check_offline_agents, "interval", minutes=2, id="offline_check", replace_existing=True)
        scheduler.add_job(cleanup_old_logs, "cron", hour=3, minute=0, id="log_cleanup", replace_existing=True)
        scheduler.add_job(cleanup_old_inventory_history, "cron", hour=3, minute=10, id="inventory_history_cleanup", replace_existing=True)
        scheduler.add_job(cleanup_old_system_history_job, "cron", hour=3, minute=20, id="system_history_cleanup", replace_existing=True)
        scheduler.add_job(check_remote_support_timeouts, "interval", seconds=30, id="rs_timeouts", replace_existing=True)
        scheduler.add_job(sync_dynamic_groups_job, "interval", seconds=15, id="dynamic_group_sync", replace_existing=True)
        scheduler.add_job(run_due_sam_report_schedules, "interval", seconds=30, id="sam_report_schedules", replace_existing=True)
        scheduler.add_job(
            check_scheduled_announcements_job,
            "interval",
            seconds=30,
            id="check_scheduled_announcements",
            replace_existing=True,
        )
        scheduler.add_job(
            check_expired_deliveries_job,
            "interval",
            seconds=60,
            id="check_expired_deliveries",
            replace_existing=True,
        )
        scheduler.start()


def stop_scheduler() -> None:
    global scheduler
    if not scheduler:
        return
    if scheduler.running:
        try:
            scheduler.shutdown(wait=False)
        except RuntimeError:
            pass
    scheduler = None
