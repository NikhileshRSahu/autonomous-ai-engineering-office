# Living Office + Runtime Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Engineering Office visually behave like a real working engineering organization, with character motion and terminal/timeline output driven exclusively by real runtime events.

**Architecture:** Add a normalized append-only runtime event layer between the existing Office engine/tool/message/model/verifier modules and the Control Room. The same event stream drives the selected-agent observable terminal, timeline/replay APIs, model-state display, and a PixiJS living floor with deterministic character identities and phase-to-room movement. Existing Office execution, safety, approvals, verification authority, universal intake, and model routing remain unchanged.

**Tech Stack:** Python 3.11+, existing Office engine, JSONL runtime event persistence, existing local HTTP server, vanilla JS/HTML/CSS control-room shell, locally bundled PixiJS 8.x (or equivalent local minified build), pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-living-office-runtime-observability-design.md`

## Global Constraints

- UI and persisted events may show only observable work: tool calls, commands, files, diffs, explicit structured hypotheses, messages, review/verification/model events; never hidden chain-of-thought.
- Independent verifier remains the only authority for PASS/FAIL; character animation cannot create or override verification state.
- Control Room remains loopback-only; replay is read-only.
- Runtime event payloads pass through existing redaction/security rules before persistence or UI exposure.
- File/diff observability is project-root scoped.
- Existing Office CLI/API behavior remains backward compatible unless a new read-only endpoint is added.
- PixiJS or equivalent rendering assets must be bundled locally; no CDN runtime dependency.
- Existing Electron security settings (`nodeIntegration: false`, `contextIsolation: true`, sandbox enabled) remain unchanged.
- `prefers-reduced-motion` must preserve information without nonessential movement.
- Floor must remain usable with at least 12 specialists at normal desktop width.

## Review Focus

1. **Secret-bearing command output/tool arguments:** event persistence and terminal rendering must redact credentials before disk/UI exposure; covered in Task 1 and Task 3 tests.
2. **Large command/test output:** browser must remain responsive via bounded terminal chunks and evidence links; covered in Task 3.
3. **Malformed/unknown runtime events:** event readers/UI must skip or safely fall back without crashing or inventing state; covered in Task 1 and Task 5.
4. **Long model cold loads and backend disconnects:** characters must show `MODEL_LOADING` or freeze at last confirmed state rather than imply progress; covered in Tasks 4 and 5.
5. **Replay safety:** historical playback must not call tools/models or mutate Office state; covered in Task 6.

---

### Task 1: Runtime Event Contract and Append-Only Store

**Files:**
- Create: `src/engineering_office/runtime_events.py`
- Modify: `src/engineering_office/security.py`
- Test: `tests/test_runtime_events.py`

**Interfaces:**
- Produces: `RuntimeEvent`, `RuntimeEventStore`, `normalize_phase(kind, payload) -> str`, `emit_runtime_event(...) -> RuntimeEvent`.
- Consumed by: Tasks 2-6.

- [ ] **Step 1: Write failing contract/store tests**

Add tests asserting:
- stable event fields (`id`, `timestamp`, `project_id`, `agent_id`, `task_id`, `kind`, `phase`, `summary`, `payload`, `severity`, `source`, `correlation_id`);
- deterministic mappings such as `file.read -> READING`, `file.written -> CODING`, `command.started -> RUNNING_COMMAND`, `test.started -> TESTING`, `review.started -> REVIEWING`, `verification.started -> VERIFYING`, `model.loading -> MODEL_LOADING`, `verification.finished(PASS) -> VERIFIED`;
- unknown event falls back safely without producing a success state;
- secret values in payload/summary are redacted before persistence;
- malformed JSONL rows are skipped with a diagnostic object rather than crashing readers;
- cursor-based incremental reads return only unseen events.

- [ ] **Step 2: Run Task 1 tests and verify RED**

Run: `pytest -q tests/test_runtime_events.py`

Expected: FAIL because `runtime_events.py`/interfaces do not exist.

- [ ] **Step 3: Implement runtime event primitives**

Create:
- `RuntimeEvent` dataclass;
- `RuntimeEventStore(project_root: Path, max_events: int = ...)` using `.office/runtime/events.jsonl`;
- `append(event)`, `read(after=None, agent_id=None, task_id=None, limit=...)`, `recent(limit=...)`;
- deterministic `normalize_phase` mapping;
- redaction through the existing security helper before serialization.

Malformed records are returned/skipped as diagnostics, never used to animate an agent.

- [ ] **Step 4: Run Task 1 tests and regression security tests**

Run: `pytest -q tests/test_runtime_events.py tests/test_tools_security.py`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/engineering_office/runtime_events.py src/engineering_office/security.py tests/test_runtime_events.py
git commit -m "feat: add runtime observability event store"
```

---

### Task 2: Instrument Authoritative Runtime Sources

**Files:**
- Modify: `src/engineering_office/office.py`
- Modify: `src/engineering_office/agent_runtime.py`
- Modify: `src/engineering_office/tools.py`
- Modify: `src/engineering_office/communications.py`
- Modify: `src/engineering_office/models_runtime.py`
- Modify: `src/engineering_office/verification.py`
- Test: `tests/test_runtime_event_integration.py`

**Interfaces:**
- Consumes: `RuntimeEventStore.emit/append` from Task 1.
- Produces: chronological real events from project/task/agent/tool/message/model/verifier boundaries.
- Consumed by: Tasks 3-6.

- [ ] **Step 1: Write failing integration tests**

Create a small temporary Office project and assert an actual run emits, in order where applicable:
- `project.discovered`, `project.staffed`, `project.planned`;
- `task.started`;
- file/tool/command/test events from real tool execution;
- `message.sent` for durable inter-agent communication;
- model lifecycle events from `LocalModelManager` event sink;
- `verification.started` then `verification.finished`;
- success phase appears only when verifier result is PASS.

Also assert a verification FAIL never emits a misleading VERIFIED state.

- [ ] **Step 2: Run integration test and verify RED**

Run: `pytest -q tests/test_runtime_event_integration.py`

Expected: FAIL because existing modules do not emit normalized runtime events.

- [ ] **Step 3: Add one event recorder boundary to `OfficeEngine`**

Expose one project-scoped event recorder/store and pass/call it from existing execution boundaries instead of creating parallel UI-specific state.

- [ ] **Step 4: Instrument tool/file/command/test execution**

Emit bounded observable facts before/after real calls. Preserve exact executed command and return code after redaction. File events use project-relative paths only.

- [ ] **Step 5: Instrument durable messages, model lifecycle and verification**

Wire `CommunicationManager`, `LocalModelManager` and verifier transitions to the same event recorder. Do not change their authority or execution semantics.

- [ ] **Step 6: Run integration + existing engine/tool/model/verifier tests**

Run: `pytest -q tests/test_runtime_event_integration.py tests/test_agent_runtime.py tests/test_tools_security.py tests/test_local_model_lifecycle.py tests/test_verification.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/engineering_office/office.py src/engineering_office/agent_runtime.py src/engineering_office/tools.py src/engineering_office/communications.py src/engineering_office/models_runtime.py src/engineering_office/verification.py tests/test_runtime_event_integration.py
git commit -m "feat: emit authoritative runtime events"
```

---

### Task 3: Observable Terminal, Files, Activity and Event APIs

**Files:**
- Modify: `src/engineering_office/ui_service.py`
- Modify: `src/engineering_office/ui_server.py`
- Test: `tests/test_runtime_observability_api.py`
- Test: `tests/test_terminal_observability.py`

**Interfaces:**
- Consumes: runtime events from Tasks 1-2.
- Produces: `DashboardService.events(...)`, `agent_terminal(agent_id, ...)`, `agent_activity(agent_id, ...)`, `replay_events(...)`, `models_runtime()` and HTTP GET endpoints.
- Consumed by: Tasks 4-6.

- [ ] **Step 1: Write failing API/service tests**

Assert:
- `GET /api/events?after=<cursor>&agent_id=&task_id=` is incremental;
- `GET /api/events/recent` returns bounded recent events;
- `GET /api/agents/<id>/terminal` returns chronological observable entries only;
- command stdout/stderr is bounded/truncated safely with evidence references when oversized;
- `GET /api/agents/<id>/activity` exposes current phase/location summary;
- `GET /api/models/runtime` reflects lifecycle events/status;
- secrets remain redacted;
- file paths outside project root are never exposed.

- [ ] **Step 2: Run observability API tests and verify RED**

Run: `pytest -q tests/test_runtime_observability_api.py tests/test_terminal_observability.py`

Expected: FAIL because read-oriented event APIs do not exist.

- [ ] **Step 3: Implement service projections**

Build terminal/files/activity projections from the same persisted events/evidence; do not maintain a separate mutable terminal log.

- [ ] **Step 4: Add read-only HTTP routes**

Add the spec endpoints with cursor/filter query parsing and existing loopback/security behavior.

- [ ] **Step 5: Run observability/API and existing UI server/service tests**

Run: `pytest -q tests/test_runtime_observability_api.py tests/test_terminal_observability.py tests/test_control_room_server.py tests/test_control_room_service.py tests/test_ui_server.py tests/test_ui_service.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/engineering_office/ui_service.py src/engineering_office/ui_server.py tests/test_runtime_observability_api.py tests/test_terminal_observability.py
git commit -m "feat: expose live runtime observability APIs"
```

---

### Task 4: Living Character Model and Local Pixi Floor

**Files:**
- Create: `src/engineering_office/ui/vendor/pixi.min.js`
- Modify: `src/engineering_office/ui/index.html`
- Modify: `src/engineering_office/ui/app.js`
- Modify: `src/engineering_office/ui/app.css`
- Test: `tests/test_living_floor_static.py`
- Test: `tests/test_living_floor_behavior.py`

**Interfaces:**
- Consumes: agent activity/events APIs from Task 3.
- Produces: deterministic agent identity, phase-to-zone destination mapping, clickable Pixi characters, room/world rendering.
- Consumed by: Tasks 5-6.

- [ ] **Step 1: Write failing static/behavior tests**

Assert production assets contain:
- local Pixi bundle reference with no CDN URL;
- semantic zones Director, Engineering, Research/Systems, Review, Robot/Simulation Lab, QA/Verification, Model Server, Break/Waiting;
- deterministic original character identity function keyed by agent id/role;
- phase-to-zone mappings required by the spec;
- at least 12 non-overlapping per-zone slots/overflow handling;
- character click selects the real agent inspector;
- reduced-motion path disables nonessential travel animation but keeps state/location text.

- [ ] **Step 2: Run floor tests and verify RED**

Run: `pytest -q tests/test_living_floor_static.py tests/test_living_floor_behavior.py`

Expected: FAIL because Pixi/world engine is not present.

- [ ] **Step 3: Bundle Pixi locally and create world layers**

Add bundled/minified PixiJS with attribution, room layers, semantic zone coordinates and hit-testing. No CDN dependency.

- [ ] **Step 4: Implement original pixel character renderer**

Generate deterministic original sprites/parts in code or local original sprite sheets. Support idle, walk, type/read, talk, research, experiment, review, model-wait, blocked, needs-user, verified visual states.

- [ ] **Step 5: Implement event-driven movement**

Move only on confirmed phase changes; backend disconnect freezes at last confirmed state and shows an explicit disconnected banner.

- [ ] **Step 6: Run living-floor + existing visual/static tests**

Run: `pytest -q tests/test_living_floor_static.py tests/test_living_floor_behavior.py tests/test_control_room_static.py tests/test_control_room_visual_polish.py tests/test_universal_intake_static.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/engineering_office/ui/vendor/pixi.min.js src/engineering_office/ui/index.html src/engineering_office/ui/app.js src/engineering_office/ui/app.css tests/test_living_floor_static.py tests/test_living_floor_behavior.py
git commit -m "feat: add event-driven living office floor"
```

---

### Task 5: Handoffs, Model Loading, Verifier and Terminal UX

**Files:**
- Modify: `src/engineering_office/ui/app.js`
- Modify: `src/engineering_office/ui/app.css`
- Modify: `src/engineering_office/ui/index.html`
- Test: `tests/test_living_office_interactions.py`
- Test: `tests/test_runtime_terminal_ui.py`

**Interfaces:**
- Consumes: Task 3 APIs and Task 4 world/character engine.
- Produces: real handoff animations, model-rack visualization, verifier semantics, selected-agent live terminal, activity timeline and bounded speech bubbles.

- [ ] **Step 1: Write failing interaction tests**

Assert:
- `message.sent` creates a bounded handoff/bubble linked to the real message;
- model `STARTING/LOADING/READY/BUSY/ERROR` changes server-rack and waiting-agent state;
- verifier success animation requires `verification.finished` with PASS;
- verification FAIL moves task/character back to working/retry state rather than success;
- terminal visibly renders actual command/file/test/message/review/model/verifier events;
- no UI template contains or synthesizes hidden chain-of-thought labels/content;
- backend disconnect stops implied movement and shows frozen-state diagnostic.

- [ ] **Step 2: Run interaction tests and verify RED**

Run: `pytest -q tests/test_living_office_interactions.py tests/test_runtime_terminal_ui.py`

Expected: FAIL because event-aware handoffs/model/verifier/live-terminal projections are incomplete.

- [ ] **Step 3: Implement handoffs and speech bubbles**

Use only durable `message.sent/received` events, cap concurrent bubbles, escape all text, and open the corresponding real message in the Messages tab.

- [ ] **Step 4: Implement model/server and verifier floor behavior**

Show long JIT loads at the server rack and waiting specialist; show PASS only after verifier event.

- [ ] **Step 5: Replace synthetic terminal with live observable stream**

Poll incrementally, append bounded entries, preserve copyability, provide evidence/file links for large payloads, and keep Files/Messages/Task/Evidence/Traces tabs intact.

- [ ] **Step 6: Run interaction/UI regression tests**

Run: `pytest -q tests/test_living_office_interactions.py tests/test_runtime_terminal_ui.py tests/test_control_room_visual_polish.py tests/test_ui_service.py tests/test_agent_controls.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/engineering_office/ui/index.html src/engineering_office/ui/app.js src/engineering_office/ui/app.css tests/test_living_office_interactions.py tests/test_runtime_terminal_ui.py
git commit -m "feat: visualize real handoffs models and terminal work"
```

---

### Task 6: Timeline and Read-Only Replay

**Files:**
- Modify: `src/engineering_office/ui_service.py`
- Modify: `src/engineering_office/ui_server.py`
- Modify: `src/engineering_office/ui/index.html`
- Modify: `src/engineering_office/ui/app.js`
- Modify: `src/engineering_office/ui/app.css`
- Test: `tests/test_runtime_replay.py`
- Test: `tests/test_activity_timeline.py`

**Interfaces:**
- Consumes: persisted events and living floor state engine.
- Produces: filtered global activity timeline and read-only historical replay over a time range.

- [ ] **Step 1: Write failing replay/timeline tests**

Assert:
- timeline filters by agent/task/event/model/error/review/verification;
- replay returns events from a bounded timestamp range;
- replay controls never invoke Office mutations/tools/models;
- scrubbing reconstructs character/inspector state from historical events;
- leaving replay returns to current live state;
- malformed historical events are skipped with diagnostic state.

- [ ] **Step 2: Run replay tests and verify RED**

Run: `pytest -q tests/test_runtime_replay.py tests/test_activity_timeline.py`

Expected: FAIL because replay/timeline contracts do not exist.

- [ ] **Step 3: Implement read-only replay service/API**

Expose historical range reads with no reference to mutation methods.

- [ ] **Step 4: Implement timeline/replay controls**

Add play/pause/scrub, filtering, and a clear visual LIVE vs REPLAY indicator. Reuse the same floor state reducer as live mode.

- [ ] **Step 5: Run replay/UI/service tests**

Run: `pytest -q tests/test_runtime_replay.py tests/test_activity_timeline.py tests/test_runtime_observability_api.py tests/test_ui_service.py`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/engineering_office/ui_service.py src/engineering_office/ui_server.py src/engineering_office/ui/index.html src/engineering_office/ui/app.js src/engineering_office/ui/app.css tests/test_runtime_replay.py tests/test_activity_timeline.py
git commit -m "feat: add runtime timeline and safe replay"
```

---

### Task 7: Accessibility, Documentation and Production Asset Packaging

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/CONTROL_ROOM_UI.md`
- Create: `docs/RUNTIME_OBSERVABILITY.md`
- Create/Update: `docs/assets/living-office-control-room.png`
- Test: `tests/test_living_office_accessibility.py`
- Test: `tests/test_living_office_release.py`

**Interfaces:**
- Consumes: final UI/event implementation.
- Produces: packaged local assets, operator/developer documentation, accessibility guarantees.

- [ ] **Step 1: Write failing accessibility/release tests**

Assert:
- keyboard-accessible roster/agent selection remains available even though the floor is canvas-rendered;
- state is expressed as text, not color only;
- `prefers-reduced-motion` path exists;
- floor has an accessible textual summary;
- Pixi/local assets are included in built wheel;
- no UI runtime asset references a CDN;
- Electron renderer security flags remain unchanged.

- [ ] **Step 2: Run tests and verify RED**

Run: `pytest -q tests/test_living_office_accessibility.py tests/test_living_office_release.py`

Expected: FAIL until accessibility/packaging/docs are completed.

- [ ] **Step 3: Complete accessibility and packaging**

Keep bottom roster/semantic controls accessible, add textual activity summary, reduced-motion handling, local vendor asset inclusion and attribution.

- [ ] **Step 4: Write operator/developer documentation**

Document runtime event contract, observable-terminal policy, no-chain-of-thought rule, replay behavior, model-loading visualization, performance limits and extension points.

- [ ] **Step 5: Capture production screenshot**

Render a seeded project with at least six specialists across engineering, research, review, model-loading and verification states and save `docs/assets/living-office-control-room.png`.

- [ ] **Step 6: Run accessibility/release tests**

Run: `pytest -q tests/test_living_office_accessibility.py tests/test_living_office_release.py tests/test_desktop_shell.py`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml docs/CONTROL_ROOM_UI.md docs/RUNTIME_OBSERVABILITY.md docs/assets/living-office-control-room.png tests/test_living_office_accessibility.py tests/test_living_office_release.py
git commit -m "docs: ship living office observability layer"
```

---

### Task 8: Whole-System Verification and Release Smoke Test

**Files:**
- No production behavior changes unless a failing regression identifies a real defect.
- Update release artifact only after all gates pass.

**Interfaces:**
- Consumes: Tasks 1-7.
- Produces: evidence that the full Office still works and the extracted release includes/serves the production living-office assets.

- [ ] **Step 1: Run full collected test inventory**

Run: `pytest --collect-only -q`

Record exact test count.

- [ ] **Step 2: Run the complete regression suite**

Run: `pytest -q` with a sufficient execution window. If nested orchestration tests exceed the environment window, split into non-overlapping groups and prove every collected test runs exactly once.

Expected: zero failures.

- [ ] **Step 3: Build wheel and clean source ZIP**

Build using the environment-compatible packaging path without weakening project requirements. Verify Pixi/runtime UI assets are inside the wheel.

- [ ] **Step 4: Install the extracted ZIP's wheel in a fresh virtual environment**

Verify:
- `office doctor`;
- offline Office demo;
- packaged UI server;
- runtime events endpoint;
- selected-agent terminal endpoint;
- production Pixi asset served locally;
- reduced-motion/static fallback;
- replay endpoint is read-only;
- loopback-only binding remains enforced.

- [ ] **Step 5: Run a seeded living-office browser/static smoke scenario**

Show at least six characters in distinct runtime phases, a real message handoff, model-loading state, command/test entries in terminal and verifier PASS transition. Capture screenshot.

- [ ] **Step 6: Verify archive cleanliness and checksum**

No `.git`, `.office`, `__pycache__`, `.pytest_cache`, `.pyc`, execution ledgers or temporary staging files in the release ZIP. Record SHA-256.

- [ ] **Step 7: Commit release metadata if tracked**

Only if the repository already tracks release metadata; otherwise artifact creation remains outside Git.

---

## Plan Self-Review

- **Spec coverage:** all 30 spec sections are mapped: event contract/persistence (Tasks 1-2), terminal/files/API (Task 3), characters/rooms/Pixi (Task 4), handoffs/director/model/verifier/terminal UX (Task 5), timeline/replay (Task 6), security/accessibility/performance/packaging/docs (Task 7), compatibility/full release acceptance (Task 8).
- **Type consistency:** `RuntimeEvent`/`RuntimeEventStore` are the single shared interface consumed by instrumentation, service projections and replay; no parallel animation log is introduced.
- **Verification independence:** Task 2 integration and Task 5 UI tests explicitly require verifier PASS before VERIFIED; model/reviewer events cannot set PASS.
- **Review-focus coverage:** all five high-risk inputs are pinned to named tests above.
- **Proportion:** eight independently testable slices; implementation details are specified by interfaces and assertions rather than copied code bodies.
