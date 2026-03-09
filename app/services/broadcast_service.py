from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Agent, Setting
from app.services.ws_manager import make_message, ws_manager


@dataclass
class BroadcastDispatchResult:
    action: str
    targeted_agents: list[str]
    skipped_agents: list[str]

    @property
    def targeted(self) -> int:
        return len(self.targeted_agents)

    @property
    def skipped(self) -> int:
        return len(self.skipped_agents)


def _normalize_platform(value: str | None) -> str:
    platform = (value or "windows").strip().lower()
    if platform not in {"windows", "linux"}:
        return "windows"
    return platform


def _settings_map(db: Session, keys: list[str]) -> dict[str, str]:
    rows = db.query(Setting).filter(Setting.key.in_(keys)).all()
    out = {row.key: (row.value or "") for row in rows}
    for key in keys:
        out.setdefault(key, "")
    return out


def _self_update_payload(platform: str, settings_map: dict[str, str]) -> dict | None:
    latest_key = f"agent_latest_version_{platform}"
    url_key = f"agent_download_url_{platform}"
    hash_key = f"agent_hash_{platform}"
    latest = (settings_map.get(latest_key) or "").strip()
    download_url = (settings_map.get(url_key) or "").strip()
    file_hash = (settings_map.get(hash_key) or "").strip()
    if not latest or not download_url or not file_hash:
        if platform == "windows":
            latest = latest or (settings_map.get("agent_latest_version") or "").strip()
            download_url = download_url or (settings_map.get("agent_download_url") or "").strip()
            file_hash = file_hash or (settings_map.get("agent_hash") or "").strip()
    if not latest or not download_url or not file_hash:
        return None
    return {
        "platform": platform,
        "latest_agent_version": latest,
        "agent_download_url": download_url,
        "agent_hash": file_hash,
    }


def dispatch_agent_broadcast(db: Session, action: str, mode: str = "normal") -> BroadcastDispatchResult:
    ws_ids = ws_manager.agent_uuids
    if not ws_ids:
        return BroadcastDispatchResult(action=action, targeted_agents=[], skipped_agents=[])

    online_rows = (
        db.query(Agent.uuid, Agent.platform)
        .filter(
            Agent.uuid.in_(ws_ids),
            Agent.status == "online",
        )
        .all()
    )
    if not online_rows:
        return BroadcastDispatchResult(action=action, targeted_agents=[], skipped_agents=list(ws_ids))

    targeted_agents: list[str] = []
    skipped_agents: list[str] = []
    if action != "self_update":
        return BroadcastDispatchResult(action=action, targeted_agents=[], skipped_agents=list(ws_ids))
    mode = (mode or "normal").strip().lower()
    if mode not in {"normal", "force"}:
        mode = "normal"

    settings_map = _settings_map(
        db,
        [
            "agent_latest_version_windows",
            "agent_download_url_windows",
            "agent_hash_windows",
            "agent_latest_version_linux",
            "agent_download_url_linux",
            "agent_hash_linux",
            "agent_latest_version",
            "agent_download_url",
            "agent_hash",
        ],
    )
    online_set = {agent_uuid for agent_uuid, _platform in online_rows}
    for ws_uuid in ws_ids:
        if ws_uuid not in online_set:
            skipped_agents.append(ws_uuid)
    for agent_uuid, raw_platform in online_rows:
        platform = _normalize_platform(raw_platform)
        payload = _self_update_payload(platform, settings_map)
        if payload is None:
            skipped_agents.append(agent_uuid)
            continue
        ws_manager.schedule_send_to_agent(
            agent_uuid,
            make_message(
                "server.broadcast.self_update",
                {
                    **payload,
                    "mode": mode,
                },
            ),
        )
        targeted_agents.append(agent_uuid)
    return BroadcastDispatchResult(action=action, targeted_agents=targeted_agents, skipped_agents=skipped_agents)
