# Universal Project Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every new Office floor enter through one secure normalization layer that accepts directories, archives, files/folders, pasted content, Git repositories, or greenfield objectives and hands the resulting local directory to the existing Office engine.

**Architecture:** Extend the existing `ProjectIntake` into a `UniversalIntakeService` that materializes non-directory sources under managed workspaces and preserves the directory-rooted OfficeEngine boundary. Add streaming upload sessions and additive `/api/intake/*` routes, then replace folder-only onboarding/New Floor with one reusable intake UI. Electron supplies narrowly scoped native pickers; browser mode uses upload sessions.

**Tech Stack:** Python 3 standard library (`pathlib`, `zipfile`, `tarfile`, `tempfile`, `subprocess`, `http.server`), existing Engineering Office service/UI, vanilla HTML/CSS/JS, Electron preload/main process, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-universal-project-intake-design.md`

## Global Constraints

- OfficeEngine remains directory-rooted; intake normalizes sources before engine construction.
- Existing `ProjectIntake.from_directory()` and `.from_zip()` callers remain compatible.
- Intake never executes project code.
- Archive/upload materialization must remain contained below managed staging/workspace roots.
- Reject archive symlinks, hardlinks, device/FIFO/special entries, absolute paths and traversal.
- Enforce `100000` files and `8 GiB` default intake limits, with tests overriding roots/limits.
- Git uses subprocess argument arrays only; credentials must be redacted from UI/provenance/errors.
- Failed imports never register a floor and partially created managed workspaces are cleaned.
- UI stays loopback-only and verifier/acceptance authority is unchanged.
- Unsupported formats fail with an actionable stable intake error code instead of fallback execution.

## Review Focus

1. Archive path aliases (`..`, absolute, backslash), TAR links/devices and malformed metadata must never escape staging.
2. Browser uploads must enforce limits incrementally and reject duplicate/unsafe relative paths before write.
3. Managed-workspace cleanup must not delete an existing user directory on failed intake.
4. Credential-bearing Git URLs must be redacted in errors, floor metadata and provenance.
5. Failed network/backend requests must preserve onboarding form state and render a useful recovery message.

---

### Task 1: Universal intake core and error model

**Files:**
- Modify: `src/engineering_office/intake.py`
- Create: `tests/test_universal_intake.py`

**Interfaces:**
- Produces `IntakeKind`, `IntakeRequest`, expanded `IntakeResult`, coded `IntakeError`, `UniversalIntakeService`, archive/root-detection helpers.
- Preserves `ProjectIntake.from_directory()` and `ProjectIntake.from_zip()` compatibility.

- [ ] Write failing tests for directory success/missing source, ZIP/TAR extraction, corrupt archive codes, traversal/link/device rejection, size/file limits, root detection, single-file import, paste, greenfield project, Git clone success/failure/redaction.
- [ ] Run `pytest -q tests/test_universal_intake.py tests/test_release_gaps.py -k 'intake or zip'` and confirm failures are feature-related.
- [ ] Implement the core interfaces and managed-workspace cleanup/provenance behavior using standard-library extractors and subprocess argument arrays.
- [ ] Re-run the intake tests and legacy ZIP tests to green.

### Task 2: Streaming browser upload sessions

**Files:**
- Modify: `src/engineering_office/intake.py`
- Create: `tests/test_intake_sessions.py`

**Interfaces:**
- Produces `IntakeSessionManager.create()`, `.upload()`, `.commit()`, `.cancel()`, `.cleanup_stale()`.
- Consumes `UniversalIntakeService` for final workspace normalization.

- [ ] Write failing tests for create/upload/commit, directory paths, duplicate/traversal rejection, incremental limits, cancel cleanup and TTL cleanup.
- [ ] Run `pytest -q tests/test_intake_sessions.py` and confirm RED.
- [ ] Implement staging/session metadata and atomic commit semantics.
- [ ] Re-run session tests to green.

### Task 3: Service integration, floor provenance and stable API errors

**Files:**
- Modify: `src/engineering_office/ui_service.py`
- Modify: `src/engineering_office/floors.py`
- Create: `tests/test_intake_service.py`

**Interfaces:**
- Produces `DashboardService.intake_path`, `.intake_paste`, `.intake_git`, `.intake_new`, `.commit_upload_session` and intake-session helpers.
- Successful intake switches service root/registers the normalized floor but does not call `start()`.

- [ ] Write failing tests that successful intake switches root without execution, failed intake leaves floor registry untouched, managed/source metadata is preserved, existing switch/open behavior stays compatible.
- [ ] Run tests and confirm RED.
- [ ] Implement service methods and provenance-aware floor registration without changing OfficeEngine execution semantics.
- [ ] Re-run service and existing floor/control-room tests to green.

### Task 4: HTTP intake routes and raw upload streaming

**Files:**
- Modify: `src/engineering_office/ui_server.py`
- Create: `tests/test_intake_api.py`

**Interfaces:**
- Adds `/api/intake/path`, `/paste`, `/git`, `/new`, `/sessions`, `/sessions/<id>/file`, `/commit`, and DELETE cancellation.
- Errors return `{error, code, message}` with 4xx status for intake/user errors.

- [ ] Write failing route tests for all JSON modes, streaming upload, commit/cancel, malformed/unsafe input, stable codes and backward-compatible `/api/project`.
- [ ] Run API tests and confirm RED.
- [ ] Implement route parsing, raw binary body handling and coded error responses.
- [ ] Re-run API plus existing server tests to green.

### Task 5: Universal Control Room intake UI

**Files:**
- Modify: `src/engineering_office/ui/index.html`
- Modify: `src/engineering_office/ui/app.css`
- Modify: `src/engineering_office/ui/app.js`
- Modify: `tests/test_control_room_static.py`
- Create: `tests/test_universal_intake_static.py`

**Interfaces:**
- One reusable onboarding/New Floor modal supports Path, Files/Archive, Paste, Git, New Project, drag/drop and objective.
- Browser file/folder selections upload via intake sessions; local path mode calls `/api/intake/path`.

- [ ] Write failing static/UI-contract tests for source tabs, drag/drop, paste multi-file controls, Git/new-project controls, shared New Floor component, progress labels, and backend-unreachable copy.
- [ ] Run static tests and confirm RED.
- [ ] Replace folder-only forms with universal intake markup/styles/controller logic while preserving user state on errors.
- [ ] Re-run static/UI tests to green and perform a Chromium render smoke check.

### Task 6: Electron native pickers

**Files:**
- Modify: `desktop/main.js`
- Modify: `desktop/preload.js`
- Modify: `tests/test_desktop_shell.py`

**Interfaces:**
- Preload exposes only `chooseProjectFolder()`, `chooseFiles()`, `chooseArchive()` plus existing non-privileged metadata.
- Main process handles picker IPC through Electron `dialog` without enabling renderer Node access.

- [ ] Write failing shell tests for picker bridge names, IPC handlers and retained `nodeIntegration:false`, `contextIsolation:true`, `sandbox:true`.
- [ ] Run desktop tests and confirm RED.
- [ ] Implement narrow picker bridge/handlers.
- [ ] Re-run desktop tests to green.

### Task 7: Configuration, docs, and release-level universal-intake smoke test

**Files:**
- Modify: `src/engineering_office/config.py`
- Modify: `README.md`
- Modify: `docs/CONTROL_ROOM_UI.md`
- Modify: `docs/OPERATIONS.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/FEATURE_MATRIX.md`
- Create: `tests/test_universal_intake_release.py`

**Interfaces:**
- Config exposes workspace/staging roots, max files/bytes and session TTL with safe defaults.
- Documentation describes all intake modes, managed workspaces and recovery/error behavior.

- [ ] Write failing config/release tests for defaults, config load overrides and packaged intake/static assets.
- [ ] Implement config wiring and documentation.
- [ ] Run all intake/UI/desktop tests, then the complete Office regression suite in bounded groups.
- [ ] Build wheel and clean ZIP, install from extracted ZIP in a fresh venv, then smoke-test direct ZIP intake, upload, paste, greenfield, Git fixture, traversal rejection and legacy folder onboarding.
