# Tabler Migration Plan (Condensed, Brand-First)

Last Updated: 2026-02-26
Owner: appcenter-server
Status: Planned / Ready to execute

---

## 1. Approved Decisions (Locked)

These decisions are confirmed and should be treated as baseline requirements:

- Tabler: pin to latest stable release.
- Color system: keep Tabler default blue palette.
- Brand: use `agent/opview_logo.png` as primary product logo.
- Visual target: high visual quality, rich use of Tabler components.
- Icons: Tabler Icons only.
- Mobile: read-mostly is enough (full feature parity not required).
- Performance: no strict benchmark target; prioritize visual quality.
- Migration model: incremental (page-by-page), not big-bang.

---

## 2. Migration Strategy

### 2.1 Core Principle

- Migrate in thin vertical slices.
- Keep backend endpoints stable while UI shell and components move to Tabler.
- Avoid breaking JS logic by preserving `data-*` selectors.

### 2.2 Rollout Order

1. Foundation (theme + layout shell + component patterns)
2. Dashboard (pilot)
3. Agents (pilot)
4. Applications
5. Deployments
6. Groups
7. Inventory
8. Settings
9. Users
10. Audit

---

## 3. Phase Plan

## Phase A - Foundation (required first)

Goal: install Tabler correctly and prepare a condensed visual baseline.

Tasks:

- [ ] Pin Tabler version in frontend asset strategy.
- [ ] Create new base layout shell (sidebar/topbar/content/footer) using Tabler structure.
- [ ] Integrate `opview_logo.png` in sidebar/topbar brand positions.
- [ ] Define condensed design tokens (spacing, table row density, form spacing, card padding).
- [ ] Keep current app color accents aligned with Tabler blue defaults.
- [ ] Validate no auth/session regressions from shell change.

Deliverables:

- Updated `app/templates/base.html`
- Updated global CSS layer (Tabler overrides + condensed tokens)
- No broken routes/pages

## Phase B - Component Layer

Goal: standardize reusable patterns before page migrations.

Tasks:

- [ ] Table pattern: toolbar + filters + density + action column + empty/loading states.
- [ ] Card/stat pattern: KPI cards + trend/meta rows.
- [ ] Form pattern: grouped sections, helper text, validation slots.
- [ ] Modal/offcanvas pattern: confirmations and quick-edit flows.
- [ ] Badge/state pattern: status consistency (online/offline, active/inactive, ok/warn/danger).
- [ ] Timeline/list-item visual pattern (for dashboard/audit).

Deliverables:

- Reusable template fragments or clear style conventions.
- Updated CSS helper classes for consistent usage.

## Phase C - Pilot Pages (Dashboard + Agents)

Goal: validate overall UX direction and condensed behavior.

Tasks:

- [ ] Dashboard:
  - [ ] Stats cards to Tabler card blocks
  - [ ] Timeline to richer Tabler list/timeline visual
  - [ ] Better spacing hierarchy and headings
- [ ] Agents:
  - [ ] Condensed data table layout
  - [ ] Action buttons grouped (detail/connect)
  - [ ] Remote/helper badges visually improved
  - [ ] Filter row upgraded with Tabler controls

Exit Criteria:

- Pilot pages stable in production.
- No JS event binding regressions.
- Approved visual direction for remaining pages.

## Phase D - Operations Pages

Goal: migrate core operational workflows with same UX language.

Pages:

- Applications
- Deployments
- Groups
- Inventory

Tasks:

- [ ] Standard table toolbar pattern on all list pages.
- [ ] Move create/edit flows to unified modal/form treatment where appropriate.
- [ ] Improve icon/media handling visuals (apps).
- [ ] Improve multi-action controls in deployments/groups.

## Phase E - Management Pages

Goal: finish management/admin area under same design language.

Pages:

- Settings
- Users
- Audit

Tasks:

- [ ] Settings grouped into visual sections with better scannability.
- [ ] Users table/filter/action density polishing.
- [ ] Audit readability upgrade (filters + detail expand + date range already present; polish visuals).

## Phase F - Final Polish

Goal: consistency, quality, and handoff confidence.

Tasks:

- [ ] Cross-page spacing and typography audit.
- [ ] Empty/loading/error states consistency.
- [ ] Mobile read-mostly pass.
- [ ] Final regression smoke checklist pass.
- [ ] Documentation final sync.

---

## 4. Tabler Components - Planned Usage Map

Use aggressively but intentionally:

- Layout: sidebar, topbar, page header, breadcrumb.
- Data views: tables, cards, badges, avatars, dropdown actions.
- Inputs: modern select/input groups, segmented controls, checkbox/radio styling.
- Overlays: modals for destructive confirmations, offcanvas for secondary detail panels.
- Signals: alerts, toasts, progress indicators, placeholders/skeleton states.
- Navigation: tabs/pills where sections are multi-state (detail/history/etc.).

Rule:

- Do not introduce components if they increase cognitive load without clear UX gain.

---

## 5. Technical Guardrails

- Keep backend API contracts unchanged during UI migration unless explicitly planned.
- Preserve existing RBAC behavior:
  - backend `require_role(...)`
  - frontend `protectPage()` + `page_roles` route guard
  - `data-required-roles` action visibility
- Prefer `data-*` selectors in JS for resilience against class changes.
- Keep incremental commits small and reversible.

---

## 6. Risks and Mitigation

- Risk: JS breakage after DOM/class refactor.
  - Mitigation: use `data-*` hooks, pilot-first rollout, smoke each page.

- Risk: visual inconsistency while migration is partial.
  - Mitigation: finish shell + component layer first, then page rollout.

- Risk: over-design reducing clarity.
  - Mitigation: prioritize hierarchy and readability over decorative complexity.

---

## 7. Testing Plan per Phase

Minimum checks after each migrated page:

- Login/session continue/logout flows
- Role visibility (viewer/operator/admin)
- List load + filter + sort + pagination
- Create/Edit/Delete critical flows (if page has mutating actions)
- Route guard redirect behavior on restricted pages

Command baseline:

```bash
./venv/bin/python -m pytest -q
```

Production smoke baseline:

- `GET /health`
- related page/api smoke for migrated scope

---

## 8. Tomorrow Resume Point

Start from **Phase A** with this exact order:

1. Tabler asset pinning and include strategy
2. Base layout shell migration (`base.html`) with brand logo placement
3. Condensed token layer (global CSS variables + spacing rules)
4. Quick smoke on login/dashboard/agents route integrity

Definition of done for tomorrow:

- Foundation merged and deployed without functional regression.
- Pilot phase (Dashboard/Agents) ready to begin immediately next session.

