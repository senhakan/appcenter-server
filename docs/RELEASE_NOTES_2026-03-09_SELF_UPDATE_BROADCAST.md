# Release Notes - 2026-03-09 (Self-Update Broadcast Hardening)

## Summary
- Removed restart/reconnect broadcast action from settings flow.
- Kept only `self_update` broadcast with explicit `mode` payload:
  - `normal`: update only when target version is newer.
  - `force`: trigger self-update pipeline even when version/hash is the same.
- Added server-side audit detail for broadcast `mode`.
- Updated settings UI to remove restart button and expose self-update mode selector.

## API/Server Changes
- `POST /api/v1/settings/agents/broadcast` now accepts only:
  - `action=self_update`
  - `mode=normal|force`
- Response message includes selected mode.
- Audit records include `mode` in details.

## Guardrails
- Restart broadcast path is fully disabled in API schema/UI flow.
- UI confirmation now clearly distinguishes `normal` vs `force` behavior.

## Live Validation Notes
- Published versions:
  - Windows `0.1.45`
  - Linux `0.1.52-live`
- Broadcast run:
  - `action=self_update, mode=normal`
  - Expected online WS agents targeted and updated.
- Post-wait metrics validated with ws stats, latest version distribution, and recent `updated_at` transitions.
