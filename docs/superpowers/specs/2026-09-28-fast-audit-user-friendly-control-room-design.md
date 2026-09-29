# Fast Audit, Model Residency, and User-Friendly Control Room Design

**Date:** 2026-09-28  
**Status:** Approved design captured for implementation planning  
**Builds on:** `2026-09-28-living-office-runtime-observability-design.md`, `2026-09-28-universal-project-intake-design.md`

## 1. Purpose

This release makes the Autonomous AI Engineering Office substantially faster for repeated local-project audits and substantially easier for a non-expert user to understand while it works.

The release combines three coordinated subsystems:

1. **Fast local-model runtime** — avoid repeated USB cold loads, batch work by model family, benchmark sleep/offload/speculative/NVFP4 options, and select only optimizations proven faster and reliable on the actual machine.
2. **Fast Audit + incremental project intelligence** — index a project once, reuse unchanged analysis safely, run cheap/high-value checks first, batch Qwen engineering work, perform one strong Nemotron review, and produce a report without modifying project source.
3. **User-friendly Control Room + run reports** — show simple progress, elapsed/stage timers, evidence-based ETA ranges, “Needs You”, human-readable activity, large living-office characters, and permanent run reports even when a run is blocked or fails.

The existing event store remains the authoritative source for live UI behavior and terminal output. The existing independent verifier remains the only component allowed to declare project acceptance PASS.

## 2. Success Criteria

A successful release must let a user import a folder/archive/new project, choose **Fast Audit** or **Check & Report**, press one Run button, and understand without reading raw logs:

- what the Office is doing now;
- which agent is doing it;
- how long the run has taken;
- how long the current stage has taken;
- whether an ETA is trustworthy yet;
- whether anything needs the user;
- whether a local model is loading/waking/sleeping;
- where the report will be written;
- what was checked, skipped, blocked, or verified;
- how to open the report, evidence, terminal, or replay.

For repeated runs, unchanged project content must not be re-sent to models merely because a new run started. Fast Audit should normally require at most one Qwen engineering residency phase and one Nemotron review residency phase, plus at most one targeted Qwen follow-up when the reviewer finds a concrete evidence gap.

## 3. Non-Goals

This release does **not**:

- weaken acceptance gates to reduce runtime;
- allow an LLM to declare PASS;
- hide failures or skipped simulation behind a success label;
- assume vLLM, TensorRT-LLM, NVFP4, or speculative decoding is faster without an A/B benchmark on the current machine;
- auto-download or install heavyweight runtimes during a normal Office run;
- copy source-project files into reports except where explicit evidence capture is allowed;
- require cloud inference;
- replace the existing local Canvas living-floor renderer merely for visual novelty.

## 4. High-Level Architecture

```text
                         USER
                          │
                    Run mode / goal
                          │
                          ▼
                    RUN COORDINATOR
              ┌───────────┼────────────┐
              │           │            │
              ▼           ▼            ▼
         Run Record   Project Index   Runtime Events
              │           │            │
              │           ▼            │
              │      Change Set         │
              │           │            │
              ▼           ▼            ▼
                   FAST AUDIT PLANNER
                          │
             ┌────────────┴────────────┐
             ▼                         ▼
       QWEN BATCH PHASE          NEMOTRON REVIEW
             │                         │
             └────────────┬────────────┘
                          ▼
                    REPORT BUILDER
                          │
        ┌─────────────────┼────────────────┐
        ▼                 ▼                ▼
   REPORT.md         SUMMARY.html      Evidence index
                          │
                          ▼
                  USER-FRIENDLY UI
       progress / timers / ETA / Needs You / replay
```

Model execution is mediated by a **Model Residency Manager** layered on the current `LocalModelManager`; it does not bypass the current PID ownership, exact-model endpoint validation, loopback restriction, or runtime events.

## 5. Run Modes

The Control Room exposes five modes:

- **Check & Report** — read-only audit; may read/search/build/test/simulate when authorized; may write only under `.office` and tool/runtime scratch locations.
- **Fast Audit** — optimized Check & Report using incremental index, cheap-first validation, model-family batching, one consolidated Nemotron review, and no full simulation unless requested or necessary to answer the audit objective.
- **Fix Issues** — normal mutable engineering run focused on detected issues.
- **Complete Project** — full existing Office workflow through independent verification and delivery.
- **Custom** — advanced policy selection.

### 5.1 Audit Write Policy

In Check & Report and Fast Audit:

Allowed:

- project reads/searches;
- build/test/simulation commands approved by existing safety policy;
- temporary build outputs that normal project tooling creates;
- `.office/index`, `.office/runs`, `.office/reports`, `.office/evidence`, `.office/benchmarks`;
- runtime scratch directories explicitly configured by the Office.

Disallowed:

- source/config/test edits;
- deletion of project files;
- commits;
- acceptance-gate mutation.

An attempted project mutation in audit mode is rejected and recorded as a policy event.

## 6. Run Record and Timer Model

Every user-initiated run gets an immutable `run_id`, for example `RUN-20260928-104112-a1b2`.

Persist:

```text
.office/runs/<run-id>/run.json
```

Required fields:

- `run_id`
- `project_id`
- `mode`
- `objective`
- `status`
- `started_at_utc`
- `finished_at_utc`
- `current_stage`
- `stage_started_at_utc`
- `stages[]`
- `report_dir`
- `model_strategy`
- `index_generation`
- `needs_user_count`
- `result_summary`

Timers shown in the UI:

1. **Total elapsed** — `now - started_at` while active; persisted final duration when complete.
2. **Current-stage elapsed** — `now - stage_started_at`.
3. **Estimated remaining** — empirical range from comparable historical runs, never a fake exact countdown.

Timer events are emitted through the existing runtime event contract so replay can reconstruct stage timing.

## 7. Stage Pipelines and Progress

### 7.1 Fast Audit / Check & Report

```text
IMPORT → INDEX → ANALYZE → TEST → REVIEW → REPORT
```

### 7.2 Complete Project

```text
DISCOVER → PLAN → IMPLEMENT → TEST → REVIEW → VERIFY → DELIVER
```

Progress is derived from real stage/task completion. The UI must not animate a fabricated percentage. A stage may be `PENDING`, `RUNNING`, `PASS`, `WARN`, `BLOCKED`, `SKIPPED`, or `FAILED`.

When a stage is deliberately skipped, the UI shows why, e.g. “Full Gazebo runtime skipped in Fast Audit; static blockers found first.”

## 8. ETA Engine

Persist historical timing samples in:

```text
.office/history/run_timings.jsonl
```

Features include:

- run mode;
- project type/domain labels;
- indexed file count;
- changed-file count;
- test count;
- requested simulation level;
- model runtime strategy;
- cold/warm model state;
- measured Qwen/Nemotron load/wake durations;
- completed stage durations.

Rules:

- With fewer than 3 comparable completed runs, display **“Learning from this run…”** rather than a numeric estimate.
- With sufficient history, show a range based on empirical comparable-run durations (default p50–p80 remaining-time band).
- The UI labels estimates as estimates and shows the sample count.
- Failed/blocked runs may contribute completed-stage timing but must not distort completion-time estimates as if they completed normally.

## 9. Permanent Run Reports

Every run, including `BLOCKED`, `FAIL`, `PARTIAL`, and audit-only runs, produces a report directory:

```text
.office/reports/<run-id>/
├── REPORT.md
├── SUMMARY.html
├── run-metadata.json
├── timeline.jsonl
├── findings.json
├── test-results.json
├── risks.json
├── model-performance.json
└── evidence/
```

Report status values:

- `AUDIT_COMPLETE`
- `PASS`
- `FAIL`
- `BLOCKED`
- `PARTIAL`

`AUDIT_COMPLETE` means the requested audit/report finished; it does **not** mean the project passed acceptance.

The report clearly distinguishes:

- inspected vs executed;
- tests actually run vs inferred/static checks;
- runtime validation vs static validation;
- skipped checks and reasons;
- blockers;
- evidence references;
- model-generated findings vs deterministic test/verification outcomes.

The existing delivery package under `.office/delivery/` remains reserved for verified project delivery semantics.

## 10. Incremental Project Index

Create:

```text
.office/index/
├── index.db
├── manifest.json
├── packages.json
├── tests.json
└── generation.json
```

SQLite is the authoritative index. It stores at minimum:

- normalized relative path;
- size;
- mtime_ns (diagnostic only);
- SHA-256 content hash;
- detected file class/language;
- package/module association;
- related tests where detectable;
- analysis generation;
- last analyzed run;
- exclusion reason where applicable.

### 10.1 Correctness Rule

Fast Audit reuse is based on content hashes, not mtime alone. Metadata may optimize candidate selection, but unchanged reuse requires a matching trusted content hash. Git metadata may improve change discovery but never replaces content/evidence checks where correctness matters.

### 10.2 Exclusions

Default excluded content includes:

- `.git/`
- `.office/` except index metadata owned by the indexer;
- virtual environments;
- dependency caches;
- build/dist artifacts unless explicitly relevant;
- model weights;
- known large binaries/media unless requested by the objective.

Exclusions are recorded, not silently forgotten.

### 10.3 Incremental Analysis Cache

Model-derived project analysis is stored by `(file_hash, analysis_schema_version, model_family, prompt_contract_version)`. A result is reusable only when all keys match. Changing the analysis contract invalidates the cache without touching the source index.

## 11. Fast Audit Planner

The Fast Audit planner consumes:

- objective;
- project map;
- current index generation;
- changed-file set;
- cached analysis;
- current model residency/benchmark data;
- available deterministic tools/tests.

It produces a read-only audit plan with this priority:

1. incremental index/update;
2. static structure/config/source inspection;
3. cheap deterministic tests/validators;
4. targeted builds/tests related to changed or high-risk areas;
5. expensive runtime/simulation only when requested or necessary;
6. evidence dossier;
7. one consolidated Nemotron adversarial review;
8. optional single targeted Qwen follow-up if review identifies a specific evidence gap;
9. report generation.

Fast Audit never loops endlessly between Qwen and Nemotron. Default model-family phase budget is:

- Qwen residency phase: 1 primary phase;
- Nemotron residency phase: 1 review phase;
- Qwen follow-up: at most 1 targeted phase.

## 12. Model-Family Batching

Extend scheduling with a model-family affinity without changing task dependency correctness.

Tasks declare or derive a preferred family:

- `qwen` — routine engineering, file/config inspection, code/test/tool work;
- `nemotron` — difficult reasoning, physics/control review, adversarial review;
- `none` — deterministic/local tool work requiring no LLM.

Among dependency-ready tasks, the scheduler prefers tasks compatible with the currently resident model family when doing so does not violate dependencies, locks, approvals, or priority constraints.

Scheduler choice must be observable via runtime events.

## 13. Model Residency Manager

Extend the current `LocalModelManager` through a residency abstraction rather than replacing its safety logic.

States:

- `COLD`
- `LOADING_USB`
- `CPU_RESIDENT`
- `GPU_READY`
- `SLEEPING`
- `WAKING`
- `BUSY`
- `ERROR`

The residency manager selects from runtime strategies proven available on the machine:

1. active model already `GPU_READY`;
2. wake sleeping/CPU-resident model;
3. warm llama.cpp mmap path / OS page cache;
4. cold storage load as final fallback.

It retains current guarantees:

- loopback-only endpoints;
- exact `/v1/models` identity check;
- model-switch mutex;
- Office-owned PID validation;
- never kill unknown processes;
- memory/resource guard before heavyweight load;
- lifecycle events and timing.

## 14. vLLM Sleep / CPU-Offload Strategy

vLLM is an **optional runtime strategy**.

The Office provides a capability probe and benchmark adapter. It does not install vLLM automatically during a normal run.

A candidate vLLM strategy is eligible only if:

- runtime import/server capability probe succeeds;
- selected model/quantization can be loaded correctly;
- sleep/wake API works;
- endpoint remains loopback-only;
- tool/structured-output benchmark remains within correctness thresholds;
- measured wake strategy is materially faster than the current llama.cpp cold/warm strategy;
- RAM guard confirms CPU-resident weights do not starve ROS/Gazebo/other required workloads.

Failed or unsupported probes record `SKIPPED_UNSUPPORTED` or `BENCHMARK_FAILED`; they do not make the Office unusable.

## 15. llama.cpp Warm-Load Strategy

The existing llama.cpp path remains the baseline and fallback.

Benchmark candidate load modes appropriate to the installed llama.cpp build, including mmap/warm page-cache behavior and, where safe, mlock/pinning configurations.

The Office records model load/wake timings so the runtime selector chooses based on measured local behavior rather than hard-coded assumptions.

## 16. Qwen Speculative-Decoding Benchmark

Add a benchmark command for the configured Qwen worker. Candidate strategies may include:

- baseline decoding;
- n-gram speculative decoding when supported;
- compatible draft-model speculative decoding when a configured draft model exists.

Representative benchmark tasks include:

- Python/code continuation;
- ROS YAML/config generation;
- URDF/Xacro-like edits;
- structured JSON/tool calls;
- shell-command planning output;
- test-failure diagnosis.

Measure:

- tokens/sec;
- time-to-first-token;
- total latency;
- speculative acceptance rate where available;
- RAM/VRAM;
- structured tool-call validity;
- output correctness against deterministic fixtures.

Default promotion rule:

- at least 15% median latency improvement across representative tasks;
- no reduction in deterministic correctness/tool-call validity;
- no material increase in crash/error rate.

Otherwise baseline decoding remains active.

## 17. Nemotron NVFP4 / TensorRT-LLM Benchmark

TensorRT-LLM/NVFP4 is an **optional challenger runtime** for the configured Nemotron model.

The Office performs a capability probe first. It must not assume laptop Blackwell support merely from GPU family naming.

Possible outcomes:

- `SUPPORTED_AND_BENCHMARKED`
- `SKIPPED_UNSUPPORTED`
- `BENCHMARK_FAILED`
- `NOT_INSTALLED`

When supported, compare the challenger against the current Nemotron llama.cpp strategy using:

- initialization success;
- load/wake time;
- VRAM/RAM;
- TTFT;
- generation throughput;
- structured output/tool behavior;
- reasoning fixture score;
- stability over repeated runs.

Automatic selection is allowed only after passing correctness and stability gates. llama.cpp remains fallback.

## 18. Runtime Benchmark Registry

Persist benchmark results in:

```text
.office/benchmarks/runtime/
├── residency.json
├── qwen-speculative.json
├── nemotron-runtime.json
└── selected-strategies.json
```

Each benchmark records:

- hardware fingerprint;
- runtime/version;
- model fingerprint;
- configuration;
- date;
- raw metrics;
- correctness result;
- selected/not-selected decision and reason.

A benchmark is invalidated when its relevant hardware/runtime/model fingerprint changes.

## 19. User-Friendly Control Room

The default Control Room becomes a simple operational view. Advanced technical panes remain available but are no longer the first surface.

### 19.1 Default Header

Show:

- project/floor name;
- `LOCAL ONLY` state;
- run mode;
- objective;
- overall run status;
- progress stages;
- total elapsed;
- current-stage elapsed;
- ETA range or learning state.

### 19.2 Living Office

Keep the event-driven floor but increase character readability and reduce decorative clutter.

Requirements:

- larger characters and labels;
- current agent activity understandable without hover;
- room occupancy derived only from real runtime events;
- model-loading wait visible at model/server area;
- blocked/needs-user state visually obvious;
- no animation implying unobserved work.

### 19.3 “What’s Happening” Panel

Default selected-agent panel begins with human-readable activity, e.g.:

> QA Engineer — Running ROS checks  
> 17 checks passed · 3 still running

Technical tabs remain one click away:

- Activity
- Terminal
- Files
- Messages
- Task
- Evidence
- Traces
- Model

### 19.4 Friendly Event Descriptions

Map normalized runtime events to plain language. Examples:

- `model.starting` → “Loading Nemotron”
- `model.ready` → “Nemotron is ready; review resumed”
- `command.started` → “Running project test command”
- `verification.finished: PASS` → “Independent verification passed”

Raw event details remain expandable.

### 19.5 Needs You

Persistent panel states:

```text
Nothing needs you right now. The Office is working.
```

or actionable cards for approvals, blocked resources, missing inputs, or explicit user decisions.

No alert is shown for normal model loading or ordinary internal handoffs.

## 20. Model-Loading User Experience

When a model transition takes time, the UI must explain it rather than looking frozen.

Example:

```text
Loading Nemotron from CPU memory
Current wait: 01:42
Previous comparable wake: 02:11
No action needed.
```

For cold storage:

```text
Cold-loading Nemotron from model storage
Previous comparable cold load: 06:14
```

A progress bar may be indeterminate unless the runtime provides a real measurable progress fraction. The UI must not fabricate percentage completion from elapsed time alone.

## 21. Completion Summary

Every finished run replaces the active view header with a concise summary:

```text
AUDIT COMPLETE
Time: 23m 51s
Files considered: 440
Changed files analyzed: 7
Checks: 24 passed · 5 warnings · 2 blockers
Qwen active time: 14m 08s
Nemotron active time: 4m 31s
```

Actions:

- Open Report
- Open Output Folder
- View Evidence
- Replay Run

In browser-only mode, “Open Output Folder” becomes a safe path reveal/copy action unless the desktop shell is available. Electron may expose the folder through a narrow approved IPC method.

## 22. Replay and Timers

Replay uses the same persisted runtime events and run record.

During replay:

- the floor moves according to historical events;
- displayed elapsed/stage timers reflect historical event time, not current wall time;
- user can scrub through the run;
- replay cannot execute tools, models, approvals, or file mutations.

## 23. APIs and Internal Interfaces

New backend concepts:

- `RunCoordinator`
- `RunRecordStore`
- `RunReportBuilder`
- `ProjectIndex`
- `IncrementalAnalysisCache`
- `FastAuditPlanner`
- `EtaEstimator`
- `ModelResidencyManager`
- runtime benchmark adapters/registry

Expected read APIs for the Control Room:

- `GET /api/run`
- `GET /api/run/timing`
- `GET /api/run/report`
- `GET /api/index/status`
- `GET /api/models/residency`
- `GET /api/needs-user`

Expected actions:

- start run with mode/objective;
- open/reveal report via local-safe desktop/browser mechanism;
- start explicit runtime benchmark;
- never expose arbitrary filesystem open commands to the renderer.

Existing `/api/events`, `/api/replay`, agent terminal, floor and model APIs remain compatible.

## 24. CLI

Add/extend commands conceptually as:

```text
office run <project> --mode fast-audit --objective "..."
office run <project> --mode check-report --objective "..."
office report <project> [--run-id ...]
office index status <project>
office index rebuild <project>
office benchmark residency <project>
office benchmark speculative qwen <project>
office benchmark nemotron-runtime <project>
```

Exact argparse shape must follow existing CLI conventions during implementation.

## 25. Safety and Verification Invariants

The following are non-negotiable:

1. Independent verification remains deterministic/test/evidence based.
2. Runtime optimization never changes acceptance criteria.
3. Fast Audit cannot modify source project files.
4. Cached model analysis is invalidated by content-hash/schema/model/prompt changes.
5. Unknown model processes are never killed.
6. Model endpoints remain loopback-only.
7. Renderer receives no arbitrary filesystem/process privilege.
8. Reports state skipped/blocked work explicitly.
9. ETA is labeled and evidence-based; no fabricated precision.
10. A report completing does not imply project acceptance PASS.

## 26. Failure Handling

Examples:

- vLLM unavailable → record unsupported; use llama.cpp.
- vLLM wake slower than baseline → do not select it.
- speculative decoding degrades correctness → disable it.
- TensorRT-LLM unsupported → record `SKIPPED_UNSUPPORTED`; use llama.cpp.
- index corruption → quarantine/rebuild index; never modify source.
- model cannot load due memory → show `Needs You` only if no automatic safe fallback remains.
- test/simulation unavailable → report `BLOCKED`/`PARTIAL` with evidence; still produce report.
- run interrupted → persist partial run record/report and allow resume/new run.

## 27. Testing Strategy

### 27.1 Run/Timer/Report Tests

Test:

- timer starts on user run;
- stage timer resets at real stage transition;
- finished duration freezes;
- interrupted/blocked runs still produce reports;
- audit completion is not acceptance PASS;
- replay uses recorded time.

### 27.2 ETA Tests

Test:

- fewer than 3 comparable runs shows learning state;
- comparable completed runs produce deterministic range fixture;
- blocked runs do not masquerade as completed duration samples;
- model cold/warm timing affects comparable bucket.

### 27.3 Index Tests

Test:

- first generation hashes/indexes project files;
- unchanged second run reuses analysis;
- one changed byte invalidates reuse;
- same-size changed file is detected by hash;
- exclusions are recorded;
- corrupted index rebuild is safe;
- `.office` and model weights do not recursively pollute analysis.

### 27.4 Audit-Mode Safety Tests

Test attempted write/delete/commit/acceptance mutation is rejected while `.office` report/index writes remain allowed.

### 27.5 Scheduler/Batching Tests

Test Qwen-ready tasks are grouped where dependency-safe, Nemotron review happens after dossier completion, and at most one default follow-up Qwen phase is scheduled in Fast Audit.

### 27.6 Residency Tests

Test state transitions, memory guard, wake-vs-cold preference, exact-model checks, owned PID behavior, unknown-process safety, and fallback selection.

### 27.7 Benchmark Tests

Use fake runtime adapters for deterministic CI coverage. Real laptop benchmark remains an environment acceptance test.

Test benchmark promotion only when speed threshold and correctness gates both pass.

### 27.8 UI Tests

Test:

- simple default view;
- progress stages from real run state;
- total/stage timers;
- ETA learning/range states;
- Needs You empty/actionable states;
- friendly event descriptions;
- terminal remains available;
- model wait explanation;
- final report actions;
- larger living-floor character readability hooks;
- reduced-motion behavior.

### 27.9 Release Tests

Fresh extracted ZIP must:

- install bundled wheel;
- run offline demo;
- start Control Room loopback-only;
- execute a deterministic Fast Audit fixture;
- build an index, rerun incrementally, and show cache reuse;
- generate report on successful audit and blocked fixture;
- serve run/timing/report/index APIs;
- preserve verifier semantics;
- contain no runtime/cache/Git leakage.

## 28. Performance Acceptance

No absolute “15–35 minute” guarantee is encoded as a release gate because local hardware/project/runtime varies.

Instead the release must demonstrate on benchmark fixtures:

- second unchanged Fast Audit performs materially fewer model-analysis calls than first run;
- batching reduces model-family switches compared with unbatched reference schedule;
- selected optional runtime optimization is enabled only if measured faster and equally correct;
- report/timer/UI overhead is negligible relative to model/test work;
- index/hash time is recorded separately from model-analysis time.

A real FactoryMate benchmark on the target laptop is the final deployment benchmark, not a unit-test requirement.

## 29. Rollout Order

Implementation order:

1. run record/timers/report directories;
2. incremental project index + analysis-cache contract;
3. Fast Audit mode + audit write policy;
4. model-family batching;
5. model residency abstraction over current local lifecycle manager;
6. vLLM sleep/offload capability benchmark;
7. Qwen speculative benchmark;
8. Nemotron TensorRT/NVFP4 capability benchmark;
9. ETA/history engine;
10. simplified Control Room + larger character polish + Needs You;
11. report/open/replay UX;
12. complete regression + extracted-release smoke tests;
13. real laptop FactoryMate A/B benchmark after installation.

## 30. Definition of Done

The release is done only when:

- every run has a durable run record and report path;
- timers and stage progress are driven by real state;
- ETA never fabricates precision and learns from history;
- Fast Audit is source-read-only;
- incremental indexing proves changed/unchanged reuse by hash;
- Qwen tasks are batched and Nemotron receives a consolidated dossier;
- model residency prefers wake/warm paths over USB cold load when benchmark-proven;
- vLLM/speculative/TensorRT options are capability-probed and benchmark-gated;
- unsupported accelerators fail gracefully to the reliable baseline;
- blocked/partial runs still create useful reports;
- user-friendly default UI explains what is happening and whether action is needed;
- advanced observable terminal remains available;
- replay uses recorded runtime timing;
- independent verifier semantics are unchanged;
- all pre-existing tests plus new tests pass;
- the extracted release artifact passes fresh-install smoke tests.
