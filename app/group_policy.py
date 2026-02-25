from __future__ import annotations

SYSTEM_GROUP_NAMES = {"store", "remote support"}


def normalize_group_name(name: str | None) -> str:
    return (name or "").strip().lower()


def is_system_group_name(name: str | None) -> bool:
    return normalize_group_name(name) in SYSTEM_GROUP_NAMES

