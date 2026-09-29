# Universal Project Intake — Design Specification

**Date:** 2026-09-28  
**Status:** Proposed for review  
**Project:** Autonomous AI Engineering Office

## 1. Goal

Replace the folder-only Control Room onboarding path with one **Universal Intake** that can create an Office floor from:

1. an existing local project directory;
2. a supported archive (`.zip`, `.tar`, `.tar.gz`/`.tgz`, `.tar.bz2`/`.tbz2`, `.tar.xz`/`.txz`);
3. one or more uploaded files;
4. an uploaded directory tree;
5. pasted code/text, with optional filenames and multiple snippets;
6. a Git repository URL;
7. a completely new project described only by an objective.

The user should not need to manually unzip, pre-create a repository, or understand internal workspace rules. Intake must be safe, local-first, explain failures clearly, and hand the normalized workspace to the existing Project Discovery → Director → Agent Factory → Verification pipeline without weakening any acceptance gate.

## 2. Non-goals / honesty boundary

“Universal” means the Office can **accept and normalize common project inputs**, not that every binary format is automatically semantically understood.

- Arbitrary uploaded files are preserved exactly.
- Text/code files are immediately available to discovery and tools.
- Binary files that require a parser the Office does not have must produce a capability warning or `BLOCKED`, never invented content.
- The first implementation will not silently invoke proprietary/untrusted archive tools. RAR/7z may be added through an explicit, separately tested extractor adapter later; unsupported formats must get an actionable error.
- Intake itself never runs project code. Execution starts only through the normal Office workflow and approval/tool policy.

## 3. Design approach

### Selected approach: normalize every new source into a real local workspace

Every intake path produces the same `IntakeResult` and ends with a concrete directory root. The existing `OfficeEngine` remains directory-based.

```text
Folder ───────────────┐
Archive ──────────────┤
Files / directory ────┤
Paste ────────────────┼──> UniversalIntakeService ──> Local Workspace ──> OfficeEngine
Git URL ──────────────┤
New project ──────────┘
```

This is preferred over teaching every Office subsystem about ZIPs/uploads because it preserves one filesystem security model, one discovery path, one verifier path, and one floor abstraction.

### Rejected approach A: UI-only special cases

Adding separate ZIP/file buttons that each manually switch the project would duplicate validation and keep the backend inconsistent. Rejected.

### Rejected approach B: virtual/in-memory projects

Keeping pasted/uploaded content in memory would break existing filesystem tools, Git/worktrees, evidence paths, and reproducibility. Rejected.

## 4. Core data model

Extend `src/engineering_office/intake.py` with:

```python
class IntakeKind(str, Enum):
    DIRECTORY = "directory"
    ARCHIVE = "archive"
    FILES = "files"
    PASTE = "paste"
    GIT = "git"
    NEW = "new"

@dataclass(slots=True)
class IntakeItem:
    relative_path: str
    size: int = 0

@dataclass(slots=True)
class IntakeRequest:
    kind: IntakeKind
    objective: str = ""
    source_path: str | None = None
    git_url: str | None = None
    pasted_items: list[dict[str, str]] = field(default_factory=list)
    display_name: str | None = None

@dataclass(slots=True)
class IntakeResult:
    root: Path
    source: str
    kind: IntakeKind
    managed: bool
    extracted_files: int
    detected_root: Path
    warnings: list[str]
```

Existing callers of `from_directory()` / `from_zip()` remain compatible where practical.

## 5. Managed workspace policy

Inputs that are already directories stay in place unless the user explicitly requests a copy.

Everything else is materialized under a managed root:

```text
~/.engineering-office/workspaces/
    <safe-slug>-<8-char-id>/
```

The root is configurable for tests and advanced users.

Properties:

- collision-safe unique directory names;
- no writes outside the managed root during import;
- partially failed imports are cleaned up;
- successful workspaces persist until the user deletes them;
- source provenance is recorded under `.office/intake.json` once the workspace exists;
- uploaded/archive source bytes are not duplicated indefinitely unless needed for evidence.

## 6. Source handling

### 6.1 Existing directory

- Resolve and require a real directory.
- Do not copy by default.
- Existing tool path/symlink protections continue to apply.
- If it already contains `.office/project.json`, UI offers **Open existing**.
- Otherwise it can be started as a new floor.

### 6.2 Local archive path or uploaded archive

Supported by Python standard library:

- ZIP;
- TAR;
- TAR.GZ / TGZ;
- TAR.BZ2 / TBZ2;
- TAR.XZ / TXZ.

Safety checks before extraction:

- maximum file count;
- maximum total declared uncompressed bytes;
- every member path remains below destination;
- reject absolute paths and `..` traversal;
- reject symlinks;
- reject hardlinks;
- reject device/FIFO/special entries;
- reject malformed archive;
- abort and clean partial workspace on failure.

Root selection:

1. ignore metadata folders such as `__MACOSX`;
2. if exactly one top-level directory exists, use it;
3. otherwise score likely project roots using markers such as `.git`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `CMakeLists.txt`, `setup.py`, ROS `package.xml`, colcon-style `src/`, and README files;
4. if one candidate clearly wins, select it;
5. if ambiguous or monorepo-like, keep the extraction root and let Project Discovery inspect the multi-root workspace rather than guessing destructively.

### 6.3 Uploaded files / directory tree

Browser mode supports:

- `Choose files`;
- `Choose folder` (`webkitdirectory` where available);
- drag/drop files and directory trees where the browser supplies relative paths.

Uploads use streaming endpoints; large files are not base64-encoded into JSON.

Per-file relative paths undergo the same containment checks as archives. Limits apply to total files/bytes across the upload session.

Electron mode additionally exposes native file/folder pickers through the preload bridge, avoiding manual path typing.

### 6.4 Paste

The UI provides a paste workspace with:

- one or more snippets;
- optional filename for each snippet;
- `Add another file`;
- objective field.

If filename is omitted:

- strong fenced-language hints may choose a conservative extension;
- otherwise use `PASTED_INPUT.txt` / `PASTED_INPUT_2.txt`, etc.;
- never invent a deep project structure before Director discovery.

All pasted text is written verbatim. The Director may then create/refactor project structure through normal tools.

### 6.5 Git repository

Accept explicit Git URLs only through the Git intake mode.

- Invoke `git` via `subprocess` argument lists, never shell interpolation.
- Clone into a managed workspace.
- Preserve repository history.
- Do not store credentials in Office config or logs.
- On authentication/network failure, return a clear error and leave no fake floor.
- Local filesystem repository paths use normal directory intake instead of `file://` cloning.
- Intake does not automatically run hooks or project commands.

### 6.6 Brand-new project

User provides:

- project name (optional);
- objective (required).

Create an empty managed workspace plus `PROJECT_BRIEF.md` containing the objective and creation timestamp. The Office then starts normally; Project Discovery sees a greenfield project and the Director creates architecture/tasks/specialists.

No acceptance criterion is fabricated. The Director must derive proposed acceptance gates and preserve user-supplied constraints.

## 7. Intake sessions for browser uploads

Add an `IntakeSessionManager` with in-process session metadata and on-disk staging.

Lifecycle:

```text
POST /api/intake/sessions
  -> session_id

POST /api/intake/sessions/<id>/file?path=<relative-path>
  Content-Type: application/octet-stream
  -> streams one file into staging

POST /api/intake/sessions/<id>/commit
  -> validates totals, materializes workspace, detects root, switches floor

DELETE /api/intake/sessions/<id>
  -> cleanup/cancel
```

Session rules:

- path containment for every file;
- max file count / total bytes;
- duplicate relative paths rejected unless explicitly replaced in the same session;
- abandoned sessions older than a configured TTL are cleaned on server start / session creation;
- commit is atomic from the UI perspective: either a usable workspace is returned or the staging directory is removed.

## 8. JSON intake endpoints

Add:

```text
POST /api/intake/path
  {"path": "...", "objective": "..."}
```

Auto-detect directory vs supported archive vs single file.

```text
POST /api/intake/paste
  {"name": "...", "objective": "...", "items": [{"path": "main.py", "content": "..."}]}
```

```text
POST /api/intake/git
  {"url": "...", "objective": "...", "name": "..."}
```

```text
POST /api/intake/new
  {"name": "...", "objective": "..."}
```

Every successful intake returns at least:

```json
{
  "root": "/real/local/workspace",
  "kind": "archive",
  "managed": true,
  "detected_root": "/real/local/workspace/project",
  "warnings": [],
  "initialized": false
}
```

The UI then calls the existing `/api/start` with the objective. Existing Office start/run/verify semantics remain unchanged.

## 9. Error contract

Replace generic UI `Failed to fetch` with actionable categories.

Server errors include:

```json
{
  "error": "IntakeError",
  "code": "ARCHIVE_UNSAFE",
  "message": "Archive contains a path outside the project workspace: ../etc/passwd"
}
```

Codes include at minimum:

- `BACKEND_UNREACHABLE` (client-side);
- `SOURCE_NOT_FOUND`;
- `UNSUPPORTED_ARCHIVE`;
- `ARCHIVE_CORRUPT`;
- `ARCHIVE_UNSAFE`;
- `LIMIT_EXCEEDED`;
- `UPLOAD_INVALID_PATH`;
- `UPLOAD_INCOMPLETE`;
- `GIT_NOT_AVAILABLE`;
- `GIT_CLONE_FAILED`;
- `OBJECTIVE_REQUIRED`;
- `WORKSPACE_CREATE_FAILED`.

The UI must show the human-readable message plus a concise recovery action. It must never display raw Python tracebacks by default.

## 10. Control Room onboarding UX

Replace the current `Project folder` modal with:

```text
OPEN A FLOOR

Drop a folder, archive or files here

[ Folder ] [ Files / Archive ] [ Paste ] [ Git ] [ New project ]

Source-specific controls

Objective
[ describe the outcome... ]

[ Open existing ] [ Create office ]
```

Behavior:

- drag/drop zone highlights on drag enter;
- selected source is summarized before creation;
- archive shows filename/size;
- folder/files show item count;
- paste shows snippet filenames;
- Git shows sanitized URL (credentials redacted);
- new project requires objective;
- progress states: `Uploading`, `Validating`, `Extracting`, `Detecting project root`, `Opening floor`, `Staffing team`;
- success transitions directly to the Office floor;
- errors remain in the modal and do not destroy user-entered objective/paste content.

`New Floor` uses the same universal intake component instead of a separate folder-only form.

## 11. Desktop shell integration

Electron preload exposes narrowly scoped methods:

```text
chooseProjectFolder()
chooseFiles()
chooseArchive()
```

The renderer never receives arbitrary Node access.

Native picker results are local paths passed to `/api/intake/path`; browser mode falls back to upload sessions.

## 12. Floor registry integration

Only successful normalized workspaces are added/touched in `FloorRegistry`.

- Failed imports never appear as floors.
- Managed floor metadata records original source kind/name.
- Switching among floors remains current behavior.
- A single normalized root cannot be opened twice concurrently in the same registry.

## 13. Security invariants

1. Intake never extracts/writes outside its destination.
2. Archive symlinks, hardlinks, devices and traversal are rejected.
3. Upload paths are relative, normalized and containment-checked.
4. File-count and byte limits apply before/while materializing.
5. Git commands use argument arrays, not shell strings.
6. Credentials are redacted from logs/UI.
7. Intake never executes project code.
8. Office UI remains loopback-only.
9. Existing acceptance snapshots and verifier immutability remain untouched.
10. New greenfield projects cannot be declared PASS without explicit/derived acceptance gates executed by the normal verifier.

## 14. Configuration

Extend `OfficeConfig` or a dedicated intake config with defaults:

```text
intake_workspace_root = ~/.engineering-office/workspaces
intake_staging_root   = ~/.engineering-office/staging
intake_max_files      = 100000
intake_max_bytes      = 8 GiB
intake_session_ttl    = 24 hours
```

Tests override these roots with temporary directories.

## 15. Observability and provenance

Record an intake event containing:

- source kind;
- sanitized source identifier;
- managed/existing workspace;
- number of files;
- bytes materialized when known;
- detected root;
- warnings;
- timestamp.

Do not record pasted source contents or secrets in global logs. Project contents stay in the project workspace.

## 16. Tests / acceptance criteria

### Unit — intake core

- existing directory succeeds;
- missing directory fails with `SOURCE_NOT_FOUND`;
- safe ZIP extracts;
- corrupt ZIP returns `ARCHIVE_CORRUPT`;
- ZIP traversal rejected;
- ZIP symlink rejected;
- TAR extraction succeeds;
- TAR traversal rejected;
- TAR symlink/hardlink/device rejected;
- archive file/byte limits enforced;
- root detection handles single-folder archive;
- root detection keeps ambiguous monorepo root;
- paste preserves bytes/text and filenames;
- unsafe pasted filename rejected;
- greenfield project creates `PROJECT_BRIEF.md`;
- Git clone success from a local test remote/repository fixture;
- Git clone failure cleans managed workspace and redacts credentials.

### Unit — upload session

- create/upload/commit flow;
- directory relative paths preserved;
- traversal rejected;
- duplicate path rejected;
- limits enforced incrementally;
- cancellation cleans staging;
- stale sessions clean up.

### Service/API

- `/api/intake/path` directory;
- `/api/intake/path` ZIP;
- `/api/intake/paste`;
- `/api/intake/git`;
- `/api/intake/new`;
- upload-session endpoints;
- successful intake switches root but does not silently start execution;
- failed intake does not register a floor;
- errors contain stable codes/messages;
- existing `/api/project` remains backward-compatible.

### UI/static

- onboarding contains universal source choices;
- new-floor dialog reuses universal intake;
- browser files/folder controls exist;
- drag/drop handlers exist;
- paste multi-file controls exist;
- Git/new-project controls exist;
- network failure is rendered as `Office backend unreachable`, not `Failed to fetch`;
- source form state survives a failed request.

### Desktop shell

- preload exposes only the picker bridge;
- native folder/file/archive pickers return paths safely;
- no Node integration in renderer.

### End-to-end release tests

From the extracted release ZIP in a fresh venv:

1. import a ZIP directly from the Control Room/API, start Office, confirm discovery succeeds;
2. upload multiple files, start Office;
3. paste a small project, start Office;
4. create a greenfield project from objective only;
5. clone a small Git fixture/repository and start Office;
6. verify a malicious traversal archive is rejected and no outside file is created;
7. verify original folder-based onboarding still works;
8. package wheel contains all UI/intake code.

## 17. Compatibility

- Existing CLI/folder workflows continue to work.
- Existing `ProjectIntake.from_directory()` and `.from_zip()` tests continue to pass.
- OfficeEngine remains directory-rooted.
- No change to verifier authority, evidence hashing, model routing, or task execution policy.
- Control Room API additions are additive; `/api/project` stays available for older clients.

## 18. Release definition

This feature is complete only when:

- every intake source above can create a normalized floor;
- the user can drag/select a ZIP without manually extracting it;
- uploaded files/folders and paste work in browser mode;
- native pickers work in the desktop shell;
- Git and greenfield modes work;
- security regression tests pass;
- `Failed to fetch` is replaced with actionable backend-unreachable messaging;
- the complete Office regression suite passes;
- the clean ZIP is installed and universal intake is smoke-tested from the extracted artifact.
