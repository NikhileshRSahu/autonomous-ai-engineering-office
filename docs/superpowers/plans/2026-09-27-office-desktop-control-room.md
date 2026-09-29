# Desktop Control Room V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** Turn the existing dashboard into a living multi-agent engineering control room with real agent inspection, steering, per-agent control, multi-project floors, and an optional Electron shell.

**Architecture:** Extend the Python service/runtime first, then rebuild the static UI over those stable APIs. Keep all authoritative execution in OfficeEngine. Electron is an optional shell that embeds the loopback UI; it does not duplicate orchestration logic.

**Tech Stack:** Python 3, stdlib HTTP server, SQLite/JSON Office state, static HTML/CSS/JS, optional Electron wrapper source.

**Spec:** `docs/superpowers/specs/2026-09-27-office-desktop-control-room-design.md`

## Global Constraints
- Local-only UI.
- Original visual design; no copied Munder assets/branding.
- No worker self-verification.
- No generic shell endpoint.
- Existing CLI/backend behavior must stay compatible.

## Review Focus
- Agent names with spaces/special characters must route safely.
- A paused/halted agent must not execute and must resume deterministically.
- Floor switching must not mix project state.
- Terminal/evidence views must never escape project/evidence scope.
- Static UI must remain functional with zero network/CDN access.

---

### Task 1: Agent controls and steering runtime
**Files:** create `src/engineering_office/agent_control.py`; modify `office.py`; tests in `tests/test_agent_controls.py`.
**Produces:** persistent agent state; `OfficeEngine.pause_agent/resume_agent/halt_agent/steer_agent`; steering injected into task context.
- [ ] Write failing tests for pause/halt/resume and steer context.
- [ ] Run tests and confirm RED.
- [ ] Implement minimal runtime support.
- [ ] Run targeted + existing office-engine tests.
- [ ] Commit.

### Task 2: Floors and agent-detail service
**Files:** create `floor_registry.py`; modify `ui_service.py`; tests in `tests/test_control_room_service.py`.
**Produces:** floor registry/list/switch; structured selected-agent detail including terminal/files/messages/task/evidence/traces/queue.
- [ ] Write failing tests.
- [ ] Verify RED.
- [ ] Implement service/data assembly with path safety.
- [ ] Verify GREEN and regression.
- [ ] Commit.

### Task 3: HTTP control-room API
**Files:** modify `ui_server.py`; tests in `tests/test_control_room_server.py`.
**Produces:** floor, agent detail, steer, per-agent control, add-agent endpoints.
- [ ] Write failing HTTP tests.
- [ ] Verify RED.
- [ ] Implement routes and URL decoding/validation.
- [ ] Verify GREEN + existing server tests.
- [ ] Commit.

### Task 4: Living office UI
**Files:** replace `ui/index.html`, `ui/app.css`, `ui/app.js`; tests in `tests/test_control_room_static.py`.
**Produces:** top chrome, office floor, inspector tabs, bottom roster, queues, steer, floor switcher, add-agent modal, feedback-state visuals.
- [ ] Write structural static tests first.
- [ ] Verify RED.
- [ ] Implement original control-room UI.
- [ ] Run static/UI server tests and JS syntax check.
- [ ] Render Chromium screenshots at desktop and mobile widths.
- [ ] Commit.

### Task 5: Optional desktop shell
**Files:** create `desktop/package.json`, `desktop/main.js`, `desktop/preload.js`, `desktop/README.md`; tests in `tests/test_desktop_shell.py`.
**Produces:** optional Electron main process that launches/attaches to `office ui --no-open`, loads loopback only, no node integration in renderer.
- [ ] Write config/syntax tests.
- [ ] Verify RED.
- [ ] Implement wrapper source.
- [ ] Verify GREEN with Node syntax checks.
- [ ] Commit.

### Task 6: Docs, release verification and ZIP
**Files:** update `README.md`, `docs/CONTROL_ROOM_UI.md`, feature matrix, screenshot assets.
**Produces:** operator instructions and new clean release ZIP.
- [ ] Update docs and feature matrix.
- [ ] Run full test matrix + compile + JS syntax + git diff check.
- [ ] Run seeded demo and UI server smoke test.
- [ ] Build clean Git archive, wheel, and extracted-archive smoke test.
- [ ] Generate checksum and handoff ZIP.
