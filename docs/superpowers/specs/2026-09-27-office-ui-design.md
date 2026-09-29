# Autonomous AI Engineering Office — User Interface Design

## Goal
Add a user-friendly local control-room interface inspired by the interaction model of Munder Difflin, while keeping an original visual design and preserving the existing Python runtime as the source of truth.

## Product shape
- `office ui [project]` launches a local dashboard in the user's browser; `--app` may open it in Chromium/Edge app mode when available.
- The dashboard is a single-page control room with a left navigation rail, project command bar, live office view, task board, activity, approvals, evidence, memory, model routing, delivery, and settings.
- No UI action may bypass the existing OfficeEngine, approval, evidence, verification, or permission boundaries.
- The UI is dependency-light and shipped as static HTML/CSS/JS inside the Python package.

## UX
### Onboarding
When no project is loaded, show a start screen with project path, objective, and Start Project action.

### Office view
Show Director summary, overall project state, progress, active specialists, their role/model/task/status, and latest activity. Agents are rendered as an original modern 'office floor' of desks/cards rather than copying Munder Difflin assets.

### Tasks
Kanban-style task board grouped by state, including dependencies, owner, risk, acceptance criteria and evidence count.

### Approvals
Prominent pending-approval inbox with action, risk, reason, Approve and Deny. High-risk actions remain blocked until explicit approval.

### Activity
Chronological event feed with task/agent context. Polling provides near-live updates without introducing a new message bus.

### Evidence and Memory
Searchable evidence list with hash/size/run metadata; searchable organizational memory showing verified versus unverified entries.

### Models
Display model profiles/routing and runtime limits from `.office/config.json`; configuration changes remain explicit and file-backed.

### Verification and Delivery
One-click Verify and Deliver actions. The UI displays independent verifier verdicts and delivery artifacts; worker claims never count as verification.

## Backend boundary
`DashboardService` is the UI-facing application service. It wraps OfficeEngine and read-only stores. `OfficeUIServer` is a localhost-only stdlib HTTP server. Long Office operations execute through a bounded `JobManager`; the UI polls jobs and snapshots.

## Security
- Bind to `127.0.0.1` by default.
- Project switching accepts existing local directories only.
- Static serving is package-resource scoped.
- File viewing is restricted to `.office` delivery/evidence paths.
- Existing approval and tool permission systems remain authoritative.
- No shell command is exposed as a generic UI endpoint.

## Views
1. Office
2. Tasks
3. Activity
4. Approvals
5. Evidence
6. Memory
7. Models
8. Delivery
9. Settings

## Acceptance
- Existing backend tests remain green.
- UI service snapshot is covered by unit tests.
- HTTP server serves dashboard and health/snapshot APIs.
- Mutating endpoints call existing Office APIs and honor approvals/control.
- `office ui --no-open --port 0` can start and stop in test mode.
- Static UI works without CDN or internet.
