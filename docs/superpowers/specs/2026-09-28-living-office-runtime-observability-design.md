# Living Office + Runtime Observability Design

**Date:** 2026-09-28  
**Status:** Approved design direction; implementation pending written-spec review  
**Project:** Autonomous AI Engineering Office  
**Scope:** Control Room visual/runtime presentation layer plus authoritative observable-work event plumbing. The Office engine, safety model, verification semantics, universal intake, model routing, and project execution architecture remain authoritative and are not replaced.

## 1. Goal

Turn the current engineering floor from a mostly static dashboard into a **living engineering office** whose characters, rooms, movement, conversations, terminal output, model activity, and verification behavior are driven by real Office events.

The user must be able to answer, at a glance and by opening the selected-agent inspector:

1. **Who is working?**
2. **What are they doing right now?**
3. **Which files/commands/tools are involved?**
4. **Who are they talking to and why?**
5. **Which model is serving the work?**
6. **What is waiting, blocked, reviewing, testing, or verifying?**
7. **What evidence exists for a claimed result?**
8. **Why is the Office apparently idle—for example, is a 30B local model loading from USB?**

The visual floor must communicate real runtime state rather than decorative animation.

## 2. Non-goals

This feature does **not**:

- replace `OfficeEngine`, `AgentRuntime`, the scheduler, feedback loop, verifier, or tool layer;
- let the UI decide PASS/FAIL;
- expose hidden chain-of-thought or fabricate model reasoning;
- turn every specialist into an OS-level PTY if that specialist is using the structured Python Office provider path;
- copy Munder Difflin characters, floor art, branding, names, or copyrighted assets;
- expose the Control Room off loopback;
- make model-generated prose authoritative evidence;
- add cloud-model dependencies;
- require Electron for the Python/browser Control Room to function.

## 3. Product principles

### 3.1 Observable work, never invented work

Every animation and terminal entry must originate from an authoritative event emitted by the Office or from persisted evidence already produced by it.

Examples of valid UI facts:

- `filesystem.read` was called on `src/foo.py`;
- `shell.run` executed `pytest tests/test_foo.py -q`;
- a task changed to `VERIFYING`;
- a message was sent from one agent to another;
- a model server entered `LOADING`;
- a patch changed `config.yaml`;
- the independent verifier returned PASS.

Examples the UI must not fabricate:

- hidden internal chain-of-thought;
- a guessed rationale not emitted in the structured agent report;
- a fake terminal command just to make the floor look busy;
- a success celebration before the verifier passes;
- a pretend conversation between agents when no durable message exists.

### 3.2 One event model, many projections

The same normalized runtime event should drive:

- the living floor;
- selected-agent terminal;
- activity timeline;
- model panel;
- messages/handoffs;
- future replay.

There must not be one UI-only animation state machine and a different terminal-only state machine that can disagree.

### 3.3 Real-world office metaphor with engineering meaning

Movement must explain engineering work rather than add noise. Examples:

- reading/writing/command execution -> assigned engineering workstation;
- research -> Research / Systems room;
- experiment/simulation -> Robot / Test Lab;
- review -> Review Room;
- independent verification -> QA / Verification room;
- user attention -> Director/front-desk attention point;
- model load/switch -> Model Server rack;
- idle -> desk idle or coffee/break zone.

### 3.4 Verification remains independent

Reviewer/model activity can interpret evidence, but only deterministic acceptance gates and the independent verifier may set authoritative PASS.

A character entering the verification room does not mean the project passed.

## 4. Architecture

```text
OfficeEngine / AgentRuntime / Tools / Messages / Model Lifecycle / Verifier
                               │
                               ▼
                    Runtime Event Normalizer
                               │
                       persistent event log
                               │
                    ┌──────────┴──────────┐
                    │                     │
             live event stream       historical replay
                    │                     │
                    ▼                     ▼
              Control Room API       Replay API
                    │
           ┌────────┼─────────┬───────────┐
           │        │         │           │
           ▼        ▼         ▼           ▼
       Living    Terminal   Timeline   Model status
        Floor     Stream      /trace     /switches
```

### 4.1 Event source boundary

`OfficeEngine` remains the source of authoritative lifecycle/task state. Tools, messaging, verification, and model lifecycle modules emit structured events through a small event recorder interface.

The event recorder must be append-only from the perspective of runtime operations. A UI refresh reads the log/state but does not mutate past events.

### 4.2 No mandatory async broker

The first version does not require Redis, NATS, Kafka, or another service. The Office is local-first and single-machine. A lightweight in-process publisher plus durable JSONL/SQLite persistence is sufficient.

The HTTP UI may poll an events endpoint initially. Server-Sent Events may be added if useful, but polling remains a supported fallback.

## 5. Runtime event contract

Create a normalized event vocabulary, for example `RuntimeEvent`:

```text
id                 stable event id
timestamp           UTC timestamp
project_id          floor/project
agent_id            optional actor
agent_role          optional role snapshot
task_id             optional task
kind                event type
phase               normalized activity phase
summary             short human-readable observable fact
payload             structured event-specific fields
severity            info | warning | error | success
source              office | tool | message | verifier | model | user
correlation_id      groups a task/tool/model transition
```

The payload must not contain secrets that existing redaction policy would hide.

### 5.1 Required event kinds

At minimum:

- `project.discovered`
- `project.staffed`
- `project.planned`
- `task.started`
- `task.state_changed`
- `agent.selected_model`
- `agent.steered`
- `tool.started`
- `tool.finished`
- `file.read`
- `file.written`
- `file.diff_available`
- `command.started`
- `command.output`
- `command.finished`
- `test.started`
- `test.finished`
- `research.started`
- `research.finished`
- `message.sent`
- `message.received`
- `review.started`
- `review.finished`
- `hypothesis.recorded`
- `hypothesis.rejected`
- `verification.started`
- `verification.finished`
- `approval.requested`
- `approval.resolved`
- `model.starting`
- `model.loading`
- `model.ready`
- `model.busy`
- `model.stopping`
- `model.stopped`
- `model.error`
- `project.blocked`
- `project.delivered`

## 6. Normalized activity phases

Runtime events map to a small visual behavior vocabulary:

- `DISCOVERING`
- `PLANNING`
- `READING`
- `CODING`
- `RUNNING_COMMAND`
- `TESTING`
- `RESEARCHING`
- `EXPERIMENTING`
- `MESSAGING`
- `REVIEWING`
- `VERIFYING`
- `MODEL_LOADING`
- `WAITING`
- `NEEDS_USER`
- `BLOCKED`
- `FAILED`
- `VERIFIED`
- `PAUSED`
- `HALTED`
- `IDLE`

The mapping is deterministic and documented. Unknown events fall back to `IDLE` or the last known safe phase; they must not create misleading animation.

## 7. Character system

### 7.1 Original pixel characters

Each dynamic specialist receives a deterministic character identity based on agent id/role. Identity includes:

- skin palette;
- hair/head silhouette;
- clothing palette;
- role accessory when appropriate;
- stable display initials/name.

No copied Office TV-show characters, Munder Difflin portraits, or third-party character assets are used.

### 7.2 Animation states

Each character must support the minimum visual states:

- idle standing/sitting;
- walking;
- seated typing;
- reading/thinking without exposing hidden reasoning;
- talking/message handoff;
- research;
- test/experiment;
- review meeting;
- model-wait/loading;
- needs-user;
- blocked/error;
- verified/success.

### 7.3 State-driven destinations

Each phase maps to a destination zone. Character motion is triggered only on actual phase changes.

Example:

```text
CODING           -> own desk
RUNNING_COMMAND  -> own desk / terminal posture
RESEARCHING      -> Research / Systems
EXPERIMENTING    -> Robot / Simulation Lab
REVIEWING        -> Review Room
VERIFYING        -> QA / Verification
MODEL_LOADING    -> Model Server rack
NEEDS_USER       -> Director / Ask-Me point
WAITING          -> own desk or break zone
```

### 7.4 Collision/readability constraints

Characters and bubbles must not overlap uncontrollably when many specialists occupy the same room. Use per-zone slots and overflow/group indicators rather than stacking sprites on the same coordinates.

The floor must remain usable with at least 12 specialists at a normal desktop width.

## 8. Room layout

The office floor should contain semantically meaningful zones:

1. **Director / Coordination**
2. **Engineering Floor**
3. **Research / Systems**
4. **Review Room**
5. **Robot / Simulation Lab**
6. **QA / Verification**
7. **Model Server area**
8. **Break / Waiting area**

The exact room geometry may adapt responsively, but the semantic zones remain stable.

## 9. Real-time terminal observability

### 9.1 Terminal purpose

The selected-agent terminal shows a chronological, human-readable stream of observable work.

It is not a chain-of-thought viewer.

### 9.2 Required entries

When available, include:

- timestamp;
- event category;
- current task;
- selected local model/provider;
- file reads/searches;
- tool names and arguments after redaction;
- commands exactly as executed;
- stdout/stderr chunks or summarized bounded output;
- return code;
- test start/result;
- file writes/diffs;
- explicit structured hypotheses emitted by the agent protocol;
- explicit rejected hypothesis events;
- durable messages/handoffs;
- review results;
- verification results;
- model load/switch events;
- blocking reason;
- approval waits.

### 9.3 Terminal output bounds

Very large outputs must not freeze the browser. Persist full evidence separately when policy allows, but terminal rendering applies per-event and total-buffer limits with expandable links to evidence/files.

### 9.4 PTY future compatibility

External CLI agents may produce true PTY output. The terminal model must accept both:

- structured Office events;
- actual PTY byte/output events from external command agents.

The inspector should merge these chronologically while preserving the source type.

## 10. Files tab

The Files tab should show:

- files read recently;
- files modified by the agent/task;
- current diff summary;
- safe inline diff preview;
- worktree/repository status when available;
- link to evidence artifact for large diffs.

It must not expose files outside the project root through the UI.

## 11. Messages and handoffs

### 11.1 Durable message source

Visual conversations come only from `CommunicationManager`/durable Office messages.

### 11.2 Floor visualization

For a new message/handoff:

- source and destination agents visually orient/move as appropriate;
- a short bubble may show a bounded summary;
- a message/envelope pulse travels between them or to the destination room;
- clicking the bubble/handoff opens the real message in the Messages tab.

Only one or a small bounded number of speech bubbles may be active at once to avoid clutter.

## 12. Director behavior

The Office Director is a real runtime actor on the floor.

Suggested mappings:

- discovery/planning -> Director workspace;
- staffing/assignment -> coordination area / relevant specialist;
- review coordination -> Review Room;
- user question/approval -> Ask-Me point;
- blocked project -> front-of-office warning state;
- delivery -> project completion board.

Director movement is driven by Director events, not a timer.

## 13. Model lifecycle visualization

The JIT Qwen/Nemotron system must be visible.

Model events should update:

- Model Server area animation;
- Models panel;
- selected-agent inspector;
- terminal/timeline.

Example sequence:

```text
10:56:21 model.stopping   Qwen
10:56:24 model.stopped    Qwen
10:56:25 model.loading    Nemotron from USB
11:02:48 model.ready      Nemotron
11:02:49 review.resumed
```

A specialist waiting on a model must show `MODEL_LOADING`, not look mysteriously idle.

The UI must distinguish:

- `STOPPED`
- `STARTING`
- `LOADING`
- `READY`
- `BUSY`
- `ERROR`

## 14. Verifier visualization

The verifier is visually distinct from workers/reviewers.

Rules:

- candidate work can move to verification only after the Office enters verification;
- the verifier character shows test/evidence activity;
- success animation occurs only after authoritative `verification.finished` with PASS;
- FAIL returns the task to an evidence-fed retry state;
- BLOCKED displays the actual blocking reason;
- Nemotron/Qwen review text is never rendered as authoritative PASS.

## 15. Activity timeline

Add a compact global timeline that can filter by:

- agent;
- task;
- event type;
- model;
- warnings/errors;
- verification/review;
- user intervention.

The timeline and terminal share the same runtime events.

## 16. Replay

### 16.1 Scope

The event log is designed so a later or same-release replay mode can reconstruct the last N minutes/hours of floor state.

Minimum replay behavior for this feature:

- choose a time range;
- play/pause;
- scrub timestamp;
- floor characters and inspector reflect historical events;
- replay is read-only and cannot trigger tools/actions.

### 16.2 Determinism

Replay should use persisted runtime events and recorded snapshots where necessary. It must not re-run model calls or engineering tools.

## 17. User controls

Existing controls remain:

- Run Office;
- Verify;
- Pause/Resume/Stop Office;
- per-agent Pause/Halt/Resume;
- Steer;
- approvals;
- universal intake/new floor.

Visual animation must never bypass these controls.

Clicking a character selects that agent and opens the same inspector used by the bottom roster.

## 18. Control Room rendering technology

### 18.1 Recommended floor renderer

Use **PixiJS** for the living floor because it provides:

- efficient 2D sprite rendering;
- deterministic coordinate/animation control;
- scalable character animation;
- room layers and hit testing;
- better performance than animating many DOM nodes.

The inspector, forms, board, approvals, memory and other application UI may remain DOM/HTML/CSS.

### 18.2 Dependency strategy

The Office must remain local-first and offline-capable after installation. PixiJS must be bundled locally in the release or built into a local UI bundle. No CDN runtime dependency is allowed.

If adding a JS build step would materially complicate the Python wheel, a bundled prebuilt/minified Pixi asset is acceptable, with license attribution.

## 19. API additions

Add read-oriented endpoints/contracts such as:

- `GET /api/events?after=<cursor>&agent_id=&task_id=`
- `GET /api/events/recent`
- `GET /api/agents/<id>/terminal`
- `GET /api/agents/<id>/activity`
- `GET /api/replay?from=&to=`
- `GET /api/models/runtime`

Existing mutation/control endpoints remain authoritative.

The event API must support incremental polling/cursors so the UI does not repeatedly download the entire event history.

## 20. Persistence

Persist normalized events under project `.office/` using an append-only store compatible with cleanup and delivery policies.

Recommended first implementation:

```text
.office/runtime/events.jsonl
```

with optional SQLite indexing if volume later requires it.

The event store must:

- rotate or cap unbounded growth;
- preserve important verifier/model/error events longer than noisy progress events;
- redact secrets before persistence;
- remain project/floor scoped.

## 21. Security and privacy

- Control Room remains loopback-only.
- Event payloads pass through secret redaction before persistence or UI exposure.
- Files/diffs are project-root scoped.
- Shell output must not bypass existing evidence redaction rules.
- UI cannot execute arbitrary commands merely by rendering an event.
- Replay is read-only.
- Speech bubbles are escaped as text, never interpreted as HTML.
- Electron renderer keeps `nodeIntegration: false`, `contextIsolation: true`, and sandboxing.
- No hidden model chain-of-thought is requested, stored, or displayed.

## 22. Performance

The living floor must remain responsive while engineering work is active.

Targets:

- floor rendering should stay interactive with at least 12 agents;
- event polling/rendering must not block command execution;
- terminal DOM should virtualize/cap old lines;
- animation pauses/throttles when tab/window is hidden;
- reduced-motion mode disables nonessential movement;
- model loading can last 10+ minutes without browser memory growth.

## 23. Accessibility

- respect `prefers-reduced-motion`;
- every character selectable by keyboard through roster/accessible list;
- color is never the only state indicator;
- status text accompanies visual state;
- speech bubbles have equivalent text in Messages/Activity;
- floor has an accessible textual summary;
- terminal remains copyable and readable without animation.

## 24. Responsive behavior

Desktop is primary, but the Control Room must degrade cleanly:

- wide desktop: floor + inspector side by side;
- narrower desktop: inspector can overlay/dock;
- bottom roster remains horizontally scrollable;
- room labels and characters scale without unreadable text;
- no critical control is hidden behind the floor canvas.

## 25. Failure behavior

Examples:

### Backend disconnected

Show:

```text
Office backend unreachable. Runtime view is frozen at the last confirmed event.
```

Do not continue character animations implying work.

### Model loading fails

Character enters `BLOCKED`/`MODEL_ERROR`; terminal shows the real model lifecycle error.

### Tool fails

Terminal shows command/tool failure and character enters the next state from Office task logic. UI must not infer project failure by itself.

### Event corruption

Skip malformed event with a visible diagnostic entry; do not crash the entire Control Room.

## 26. Testing strategy

### 26.1 Event contract tests

Verify:

- tool events map to correct phases;
- message events produce handoffs;
- model lifecycle maps correctly;
- verifier PASS alone triggers verified state;
- secrets are redacted;
- malformed events do not crash readers.

### 26.2 Runtime integration tests

Execute a small Office task and assert chronological events for:

```text
task start
file read
command/test
file write
review
verification
```

### 26.3 Terminal tests

Verify exact observable commands, file paths, outputs, model switches and results are rendered, and hidden chain-of-thought is not invented.

### 26.4 Floor behavior tests

Verify phase -> destination/animation mapping and that agent selection remains correct after movement.

### 26.5 Model JIT tests

Verify a long model load shows `MODEL_LOADING`, exact model readiness, and resumes the waiting specialist.

### 26.6 Replay tests

Verify replay is read-only, uses historical events, and cannot cause tool execution.

### 26.7 Accessibility tests

Verify reduced-motion behavior, textual state labels, keyboard selection path, and safe text rendering.

### 26.8 Regression

All existing Office, universal intake, local-model lifecycle, verifier, security, scheduler and CLI tests remain green.

## 27. Acceptance criteria

The feature is accepted only when all of the following are demonstrated:

1. A fresh project can be opened and staffed normally.
2. At least six dynamically created specialists appear as distinct original characters.
3. Clicking a floor character selects the correct real agent.
4. Characters move only because actual runtime phase changes occurred.
5. Coding/file/command activity is shown in the selected-agent terminal from real tool evidence.
6. Agent-to-agent durable messages produce visible handoffs and open the real message on click.
7. Research, review, experiment and verification move characters to the appropriate semantic rooms.
8. A local-model cold load visibly shows model loading rather than apparent idle time.
9. The terminal shows model start/ready/switch events.
10. Verifier PASS is required before verified/success animation.
11. Failed verification visibly returns the task to a retry/working state.
12. Reduced-motion mode makes the same information available without movement.
13. Event persistence survives Control Room refresh.
14. Replay of recorded events does not execute any tool/model action.
15. No chain-of-thought is fabricated or exposed.
16. Existing loopback/security/approval/verification boundaries remain intact.
17. Full repository regression suite passes.
18. Extracted release package is smoke-tested with the production UI assets.

## 28. Delivery artifacts

The implementation should update/create at minimum:

```text
src/engineering_office/runtime_events.py
src/engineering_office/ui_service.py
src/engineering_office/ui_server.py
src/engineering_office/agent_runtime.py
src/engineering_office/tools.py
src/engineering_office/communications.py
src/engineering_office/models_runtime.py
src/engineering_office/verification.py
src/engineering_office/ui/index.html
src/engineering_office/ui/app.js
src/engineering_office/ui/app.css
src/engineering_office/ui/vendor/pixi.min.js   (or equivalent local bundle)
docs/CONTROL_ROOM_UI.md
docs/RUNTIME_OBSERVABILITY.md
docs/assets/living-office-control-room.png
```

Exact files may be adjusted during planning when existing module boundaries make a smaller change more correct.

## 29. Migration and compatibility

Projects created by older Office versions may have no runtime event log. The UI must continue to work by deriving an initial snapshot from existing task/agent/evidence state, then record new events from that point forward.

Existing CLI behavior and APIs should remain compatible unless the implementation plan explicitly introduces a versioned endpoint.

## 30. Final product behavior

The intended user experience is:

```text
User gives project
      ↓
Director discovers it
      ↓
real specialist characters arrive
      ↓
characters go to desks/rooms based on actual work
      ↓
user clicks any specialist
      ↓
sees real commands/files/tests/messages/model state in terminal
      ↓
reviewers visibly meet / exchange evidence
      ↓
local model loading is visible at server rack
      ↓
verifier runs actual acceptance gates
      ↓
PASS only after evidence-backed verification
      ↓
office returns to verified/idle state
```

The result should feel like supervising a real engineering organization while preserving the scientific honesty and independent verification that distinguish the Engineering Office from a purely theatrical multi-agent UI.
