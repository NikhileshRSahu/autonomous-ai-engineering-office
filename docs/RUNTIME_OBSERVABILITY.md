# Runtime Observability and Living Office

The Control Room visualizes **observable engineering work only**. Every character state, terminal entry, handoff, model indicator, and replay frame comes from the append-only runtime event stream stored at `.office/runtime/events.jsonl`.

## Event contract

Each event contains a stable id, UTC timestamp, project id, optional agent/task ids, kind, normalized phase, human-readable summary, structured payload, severity, source, and optional correlation id. Secrets are redacted before persistence.

The main phases are `DISCOVERING`, `PLANNING`, `READING`, `CODING`, `RUNNING_COMMAND`, `TESTING`, `RESEARCHING`, `EXPERIMENTING`, `MESSAGING`, `REVIEWING`, `VERIFYING`, `MODEL_LOADING`, `WAITING`, `NEEDS_USER`, `BLOCKED`, `FAILED`, `VERIFIED`, `PAUSED`, `HALTED`, and `IDLE`.

## What the terminal shows

The selected-agent terminal is a projection of real events such as file reads/writes, shell commands, bounded stdout/stderr, durable messages, model lifecycle transitions, review events, and independent-verifier results. Large output is truncated in the browser while evidence remains on disk.

It does **not** display or invent hidden chain-of-thought. Structured hypotheses explicitly emitted by agents may be shown because they are part of the Office's output contract, not private reasoning traces.

## Character behavior

Characters move only when a confirmed runtime phase changes. Engineering work maps to workstations, research to Research / Systems, experiments/tests to the Robot Lab, review to the Review room, independent verification to Verification, model cold-load waiting to the Model Server rack, and blocked/idle work to the waiting area.

The floor uses original programmatically rendered pixel engineers. No third-party character art is required at runtime.

## Messages and handoffs

Only durable `message.sent` events create handoff lines or bubbles. Clicking the corresponding specialist keeps the real message history available in the inspector.

## Verification authority

A character entering the Verification room is **not** a PASS. `VERIFIED` is emitted only after `verification.finished` reports `PASS` from the independent verifier. Review/model opinions cannot set PASS.

## Models

Local model lifecycle events (`model.starting`, `model.loading`, `model.ready`, `model.error`, and related transitions) are reflected at the Model Server rack. Long USB cold loads therefore look like model loading rather than mysterious idle time.

## Replay

Timeline replay reads historical events only. Replay APIs never invoke tools, models, or Office mutations. LIVE and REPLAY modes share the same state reducer so the historical floor uses the same semantics as current activity.

## Accessibility and reduced motion

The canvas is supplemental. The bottom agent roster, inspector, activity text, controls, and state labels remain semantic HTML. `prefers-reduced-motion: reduce` disables nonessential travel/animation while keeping location and state text available.

## Security

The Control Room remains loopback-only. Event persistence uses the same secret redaction policy as evidence. File paths exposed through observability are restricted to project-relative paths; paths outside the project root are dropped from UI projections.

## Extension points

New tools or subsystems should emit observable facts through the runtime event recorder rather than writing directly to UI state. Add a deterministic `kind -> phase` mapping only when the new event has a clear physical meaning. Unknown events safely fall back without creating success states.
