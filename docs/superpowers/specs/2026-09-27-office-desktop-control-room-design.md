# Autonomous AI Engineering Office — Desktop Control Room V2

## Goal
Replace the dashboard-first UI with an original desktop engineering control room inspired by the interaction strengths of Munder Difflin: a living office floor, persistent agent roster, selected-agent console, queue/steer controls, multi-project floors, and visible review/verification flow. Preserve the Python Office engine as the authority.

## Non-goals
- Do not copy Munder Difflin branding, characters, artwork, floor map, or source assets.
- Do not weaken approval, evidence, verification, or project-root safety rules.
- Do not require cloud services or a CDN.

## Primary layout
A single full-window workspace has four persistent regions:
1. top chrome: project/floor switcher, objective/state, run/verify controls;
2. left office floor: spatial rooms/desks generated from the active specialist roster and runtime state;
3. right agent inspector: selected agent identity, status, model, task, per-agent controls, steer input, and tabs Terminal/Files/Messages/Task/Evidence/Traces;
4. bottom roster: Director plus every specialist and Add Agent.

## Floor behavior
Each local project is a floor. A floor owns its own `.office` data, team, tasks, memory, evidence and model config. The control room keeps a local recent-floor registry and switches the active `DashboardService` root without mixing state between projects.

## Agent selection and inspector
Selecting a desk or roster card selects the agent. The inspector is derived from actual Office state:
- task and task state;
- messages to/from the agent;
- task events/traces;
- task evidence;
- touched files from Git status scoped to the project;
- terminal transcript reconstructed from execution evidence and tool results;
- queue = messages addressed to the agent.
The Director is a special selectable actor with project-level events/messages instead of a task terminal.

## Steering
`Steer` persists a structured USER→agent message. Active task execution includes current steering/inbox messages in model context on every iteration, so steering is operational rather than decorative.

## Per-agent control
Persist per-agent state (`running`, `paused`, `halted`). Scheduler/task execution refuses to start work owned by a paused/halted agent and records a blocked reason. Resuming an agent can reset its blocked owned tasks to `ASSIGNED`.

## Feedback visualization
Agent states visibly distinguish investigating, experimenting, implementing, awaiting review, verifying, verified, rejected/blocked and idle. The office floor and inspector derive these states from task state/events; no simulated success state may override verifier output.

## Desktop shell
Keep `office ui` as the dependency-light localhost application. `office ui --app` opens the same control room in Chromium/Edge app mode when available. Add an optional `desktop/` Electron wrapper source package that starts/attaches to the local Office UI and opens a native window; the Python package remains usable without Node/Electron.

## API additions
- GET `/api/floors`
- POST `/api/floors` `{path}`
- GET `/api/agents/{name}`
- POST `/api/agents/{name}/steer` `{message}`
- POST `/api/agents/{name}/control/{pause|resume|halt}`
- POST `/api/add-agent` `{expertise}`
All mutations route through service/engine boundaries.

## Security
- UI remains loopback-only.
- Floor roots must be existing directories.
- Agent detail never reads outside project root or `.office` evidence/delivery.
- Steering is context, not an unrestricted shell endpoint.
- Per-agent controls cannot bypass acceptance gates.
- Electron wrapper loads only the local loopback URL and disables node integration in renderer.

## Acceptance
- Existing tests remain green.
- New service tests prove floors, agent detail, steering, and per-agent control.
- New HTTP tests prove API routing and name/path validation.
- UI static tests assert the four-region control-room structure and required tabs.
- Runtime test proves steer messages reach agent context.
- Runtime test proves paused/halted agents are not executed and resume can requeue owned tasks.
- Electron wrapper source passes syntax/config checks without requiring Electron installation.
- Extracted release still runs offline demo and UI smoke test.
