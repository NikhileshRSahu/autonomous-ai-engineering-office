# Fast Audit + Model Residency + User-Friendly Control Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add measured fast-audit execution, incremental project intelligence, benchmark-gated local-model residency optimizations, durable run reports/timers/ETA, and a simpler user-facing Control Room without weakening verification.

**Architecture:** The existing Office engine, runtime-event store, local-model lifecycle manager, universal intake, living-floor renderer, and independent verifier remain authoritative. New run/index/audit/residency/report services are narrow modules consumed by `OfficeEngine`, `ControlRoomService`, CLI, and scheduler; optional vLLM/speculative/TensorRT paths are capability probes and benchmark challengers that fall back to the current llama.cpp path unless they are both faster and equally correct.

**Tech Stack:** Python 3.11+, stdlib SQLite/JSON/subprocess/threading, existing local HTTP server, existing Canvas Control Room, pytest, optional external llama.cpp/vLLM/TensorRT-LLM detected at runtime but never required for CI.

**Spec:** `docs/superpowers/specs/2026-09-28-fast-audit-user-friendly-control-room-design.md`

## Global Constraints

- Independent verification remains deterministic/test/evidence based; no model may declare project acceptance PASS.
- `check-report` and `fast-audit` are source-read-only; writes are limited to `.office` and explicitly configured scratch/build outputs.
- Model endpoints remain loopback-only and unknown model processes are never killed.
- Cache reuse requires matching content hash, analysis schema version, model family, and prompt-contract version.
- Optional vLLM/speculative/TensorRT-NVFP4 optimizations are benchmark-gated and must fall back cleanly when unsupported, slower, or less correct.
- ETA is an empirical range; with fewer than three comparable completed runs the UI says `Learning from this run…`.
- Every run, including `BLOCKED`, `FAIL`, and `PARTIAL`, gets a durable run record and report directory.
- Runtime events remain the authoritative source for live terminal/floor/replay behavior; no hidden reasoning text is exposed.
- Existing universal intake, living-floor, security, audit, and verifier behavior must remain backward compatible.

## Review Focus

1. **Same-size/same-mtime source changes:** Task 2 tests that SHA-256, not metadata alone, invalidates index/cache reuse.
2. **Audit-mode mutation attempts through non-obvious tools:** Task 3 tests write/delete/git/acceptance changes are denied while `.office` report/index writes remain allowed.
3. **Optional runtime present but slower/incorrect:** Tasks 6–7 test benchmark rejection and baseline fallback rather than enabling an optimization because it is installed.
4. **Interrupted/blocked runs:** Tasks 1 and 9 test frozen durations, partial stage history, and useful report generation without implying PASS.
5. **Concurrent ready tasks with different model families:** Task 4 tests affinity batching never violates dependencies, locks, approvals, or deterministic-task priority.

---

### Task 1: Durable Run Records, Stages, and Timers

**Files:**
- Create: `src/engineering_office/run_records.py`
- Modify: `src/engineering_office/office.py`
- Modify: `src/engineering_office/ui_service.py`
- Test: `tests/test_run_records.py`

**Interfaces:**
- Produces: `RunStageState`, `RunRecord`, `RunRecordStore`, `RunCoordinator`.
- `RunCoordinator.start(mode: str, objective: str, stages: list[str]) -> RunRecord`
- `RunCoordinator.transition(stage: str, state: str, detail: str | None = None) -> RunRecord`
- `RunCoordinator.finish(status: str, summary: dict[str, Any] | None = None) -> RunRecord`
- `RunCoordinator.timing(now: datetime | None = None) -> dict[str, Any]`
- Persists `.office/runs/<run-id>/run.json` and emits normalized runtime events for run/stage transitions.

- [ ] **Step 1: Write failing run-record tests** for unique run IDs, total/stage elapsed time, stage-reset behavior, finish-duration freeze, interrupted/blocked status, and event emission.
- [ ] **Step 2: Run** `pytest -q tests/test_run_records.py` **and confirm RED** because the module/interfaces do not exist.
- [ ] **Step 3: Implement** `run_records.py` and minimally wire `OfficeEngine`/`ControlRoomService` to expose the active run without changing existing `OfficeEngine.run()` semantics.
- [ ] **Step 4: Run** `pytest -q tests/test_run_records.py tests/test_runtime_events.py tests/test_runtime_event_integration.py tests/test_office_engine.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: add durable run records and timers`.

### Task 2: Incremental Project Index and Analysis Cache

**Files:**
- Create: `src/engineering_office/project_index.py`
- Modify: `src/engineering_office/discovery.py`
- Test: `tests/test_project_index.py`

**Interfaces:**
- Consumes: project root and run ID from Task 1.
- Produces: `ProjectIndex`, `IndexGeneration`, `IndexUpdate`, `IncrementalAnalysisCache`.
- `ProjectIndex.update() -> IndexUpdate` where update exposes `generation`, `changed`, `unchanged`, `removed`, `excluded`.
- `ProjectIndex.status() -> dict[str, Any]`.
- `IncrementalAnalysisCache.get(file_hash: str, schema_version: str, model_family: str, prompt_contract_version: str) -> dict[str, Any] | None`.
- `IncrementalAnalysisCache.put(...) -> None`.

- [ ] **Step 1: Write failing index tests** for first index, unchanged reuse, one-byte change, same-size/same-mtime change, removal, default exclusions, recorded exclusions, safe corrupt-index rebuild, and cache-key invalidation.
- [ ] **Step 2: Run** `pytest -q tests/test_project_index.py` **and confirm RED**.
- [ ] **Step 3: Implement** SQLite-backed index under `.office/index/` with SHA-256 as correctness authority; metadata may avoid unnecessary reads only when a trusted prior hash is revalidated as required by the tests.
- [ ] **Step 4: Run** `pytest -q tests/test_project_index.py tests/test_discovery_agents.py tests/test_release_gaps.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: add incremental project index`.

### Task 3: Check & Report / Fast Audit Policy and Planner

**Files:**
- Create: `src/engineering_office/fast_audit.py`
- Modify: `src/engineering_office/tools.py`
- Modify: `src/engineering_office/office.py`
- Test: `tests/test_fast_audit.py`
- Test: `tests/test_audit_mode_safety.py`

**Interfaces:**
- Consumes: `IndexUpdate`, project map, objective, available tests/tools, current model-family strategy.
- Produces: `AuditModePolicy`, `FastAuditPlan`, `FastAuditPlanner`.
- `AuditModePolicy.authorize(tool_name: str, args: dict[str, Any]) -> tuple[bool, str | None]`.
- `FastAuditPlanner.plan(...) -> FastAuditPlan` with stages `IMPORT, INDEX, ANALYZE, TEST, REVIEW, REPORT` and phase budget `qwen=1`, `nemotron=1`, `qwen_followup<=1`.

- [ ] **Step 1: Write failing policy/planner tests** for read/search/build/test allowance, source write/delete/git/acceptance denial, `.office` output allowance, cheap-first ordering, simulation skip reasons, one consolidated Nemotron review, and at-most-one Qwen follow-up.
- [ ] **Step 2: Run** `pytest -q tests/test_fast_audit.py tests/test_audit_mode_safety.py` **and confirm RED**.
- [ ] **Step 3: Implement** the planner/policy and inject the policy at the existing tool authorization boundary; do not create a second executor.
- [ ] **Step 4: Run** `pytest -q tests/test_fast_audit.py tests/test_audit_mode_safety.py tests/test_tools_security.py tests/test_verification.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: add read-only fast audit mode`.

### Task 4: Model-Family Affinity and Qwen/Nemotron Batching

**Files:**
- Modify: `src/engineering_office/scheduler.py`
- Modify: `src/engineering_office/planning.py`
- Modify: `src/engineering_office/models.py`
- Test: `tests/test_model_family_batching.py`

**Interfaces:**
- Consumes: existing task dependency graph and a preferred family `qwen | nemotron | none`.
- Produces: `Scheduler.next_batch(..., preferred_model_family: str | None = None)` behavior that prefers compatible ready tasks without violating existing dependency/write-lock/priority rules.
- Deterministic `none` work remains eligible without forcing a model switch.

- [ ] **Step 1: Write failing batching tests** for Qwen grouping, single Nemotron review phase, deterministic-task eligibility, dependency barriers, lock conflicts, approval blocks, and anti-starvation fallback.
- [ ] **Step 2: Run** `pytest -q tests/test_model_family_batching.py` **and confirm RED**.
- [ ] **Step 3: Implement** family affinity using existing scheduler readiness/lock checks; emit scheduling-choice runtime events.
- [ ] **Step 4: Run** `pytest -q tests/test_model_family_batching.py tests/test_planning_scheduler.py tests/test_parallel_office.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: batch tasks by local model family`.

### Task 5: Model Residency Abstraction over LocalModelManager

**Files:**
- Modify: `src/engineering_office/models_runtime.py`
- Test: `tests/test_model_residency.py`
- Test: `tests/test_local_model_lifecycle.py`

**Interfaces:**
- Consumes: existing `LocalModelManager`, `LocalModelSpec`, PID ownership, exact-model checks and lifecycle events.
- Produces: `ResidencyState` enum and `ModelResidencyManager`.
- `ModelResidencyManager.ensure(name: str) -> dict[str, Any]`
- `ModelResidencyManager.sleep(name: str) -> dict[str, Any]`
- `ModelResidencyManager.wake(name: str) -> dict[str, Any]`
- `ModelResidencyManager.status(name: str) -> dict[str, Any]`
- Selection priority: GPU-ready → sleeping/CPU-resident wake → warm llama path → cold load.

- [ ] **Step 1: Write failing residency tests** for state transitions, wake-vs-cold preference, memory guard, exact-model conflict, owned-PID behavior, unknown-process refusal, serialized concurrent switching, and timing events.
- [ ] **Step 2: Run** `pytest -q tests/test_model_residency.py tests/test_local_model_lifecycle.py` **and confirm RED only for new behavior**.
- [ ] **Step 3: Implement** `ModelResidencyManager` as a wrapper/extension around the existing manager; preserve all existing safety checks.
- [ ] **Step 4: Run** `pytest -q tests/test_model_residency.py tests/test_local_model_lifecycle.py tests/test_model_runtime.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: add benchmark-aware model residency`.

### Task 6: Runtime Benchmark Registry, vLLM Sleep Probe, and llama.cpp Warm-Load Baseline

**Files:**
- Create: `src/engineering_office/runtime_benchmarks.py`
- Modify: `src/engineering_office/models_runtime.py`
- Test: `tests/test_runtime_benchmarks.py`

**Interfaces:**
- Produces: `RuntimeBenchmarkRegistry`, `BenchmarkDecision`, `VllmSleepBenchmark`, `LlamaWarmLoadBenchmark`.
- `RuntimeBenchmarkRegistry.record(kind: str, result: dict[str, Any]) -> None`
- `RuntimeBenchmarkRegistry.selected(kind: str) -> dict[str, Any] | None`
- Benchmark fingerprints include hardware/runtime/model/config.
- Candidate statuses include `SUPPORTED_AND_BENCHMARKED`, `SKIPPED_UNSUPPORTED`, `BENCHMARK_FAILED`, `NOT_INSTALLED`.

- [ ] **Step 1: Write failing fake-adapter benchmark tests** for capability failure, successful sleep/wake, slower-than-baseline rejection, correctness-gate rejection, fingerprint invalidation, RAM-guard rejection, and llama warm-load fallback.
- [ ] **Step 2: Run** `pytest -q tests/test_runtime_benchmarks.py` **and confirm RED**.
- [ ] **Step 3: Implement** benchmark adapters using dependency injection/subprocess boundaries so CI never needs vLLM or real 30B models; normal Office runs never install runtimes.
- [ ] **Step 4: Run** `pytest -q tests/test_runtime_benchmarks.py tests/test_model_residency.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: benchmark local model residency strategies`.

### Task 7: Qwen Speculative and Nemotron TensorRT/NVFP4 Challengers

**Files:**
- Modify: `src/engineering_office/runtime_benchmarks.py`
- Modify: `src/engineering_office/cli.py`
- Test: `tests/test_inference_challenger_benchmarks.py`
- Test: `tests/test_cli_model_benchmarks.py`

**Interfaces:**
- Produces: `QwenSpeculativeBenchmark`, `NemotronRuntimeBenchmark` and CLI commands following existing parser conventions.
- Qwen promotion requires >=15% median latency improvement, unchanged deterministic/tool-call correctness, and no material stability regression.
- Nemotron challenger outcomes include unsupported/not-installed without failing the Office; llama.cpp remains fallback.

- [ ] **Step 1: Write failing benchmark/CLI tests** for baseline/n-gram/draft candidates, 15% threshold, correctness rejection, TensorRT capability skip, NVFP4 challenger comparison, and selected-strategy persistence.
- [ ] **Step 2: Run** `pytest -q tests/test_inference_challenger_benchmarks.py tests/test_cli_model_benchmarks.py` **and confirm RED**.
- [ ] **Step 3: Implement** deterministic benchmark orchestration and CLI entry points; external runtimes are probed, never assumed or auto-installed.
- [ ] **Step 4: Run** `pytest -q tests/test_inference_challenger_benchmarks.py tests/test_cli_model_benchmarks.py tests/test_cli_demo.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: add inference challenger benchmarks`.

### Task 8: Historical ETA Estimator

**Files:**
- Create: `src/engineering_office/eta.py`
- Modify: `src/engineering_office/run_records.py`
- Test: `tests/test_eta_estimator.py`

**Interfaces:**
- Produces: `RunTimingSample`, `EtaEstimate`, `EtaEstimator`.
- `EtaEstimator.record(record: RunRecord, features: dict[str, Any]) -> None`
- `EtaEstimator.estimate(active_record: RunRecord, features: dict[str, Any]) -> EtaEstimate`
- Persists `.office/history/run_timings.jsonl`.
- Fewer than 3 comparable completed runs returns `state="LEARNING"`; otherwise returns p50–p80 remaining range with sample count.

- [ ] **Step 1: Write failing ETA tests** for learning state, deterministic p50–p80 fixture, blocked-run exclusion from completion-duration population, completed-stage reuse, warm/cold model bucketing, and replay/final-duration behavior.
- [ ] **Step 2: Run** `pytest -q tests/test_eta_estimator.py` **and confirm RED**.
- [ ] **Step 3: Implement** estimator and timing persistence without inventing progress percentages.
- [ ] **Step 4: Run** `pytest -q tests/test_eta_estimator.py tests/test_run_records.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: add empirical run ETA ranges`.

### Task 9: Permanent Reports, Completion Semantics, and Read APIs

**Files:**
- Create: `src/engineering_office/reporting.py`
- Modify: `src/engineering_office/ui_service.py`
- Modify: `src/engineering_office/ui_server.py`
- Test: `tests/test_run_reporting.py`
- Test: `tests/test_run_api.py`

**Interfaces:**
- Consumes: `RunRecord`, runtime events, index stats, findings/tests/risks/model metrics.
- Produces: `RunReportBuilder.build(...) -> Path` writing `.office/reports/<run-id>/` with `REPORT.md`, `SUMMARY.html`, `run-metadata.json`, `timeline.jsonl`, `findings.json`, `test-results.json`, `risks.json`, `model-performance.json`, `evidence/`.
- Adds read APIs: `GET /api/run`, `/api/run/timing`, `/api/run/report`, `/api/index/status`, `/api/models/residency`, `/api/needs-user`.
- `AUDIT_COMPLETE` never maps to verification PASS.

- [ ] **Step 1: Write failing report/API tests** for audit complete, pass/fail/blocked/partial, interrupted runs, skipped-check disclosure, evidence references, safe report-path access, and no PASS implication.
- [ ] **Step 2: Run** `pytest -q tests/test_run_reporting.py tests/test_run_api.py` **and confirm RED**.
- [ ] **Step 3: Implement** reporting and read-only APIs; extend `office_file()` allowlist to reports using the same traversal protections.
- [ ] **Step 4: Run** `pytest -q tests/test_run_reporting.py tests/test_run_api.py tests/test_ui_server.py tests/test_verification.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: add permanent run reports and APIs`.

### Task 10: User-Friendly Control Room, Timers, Needs You, and Larger Characters

**Files:**
- Modify: `src/engineering_office/ui/index.html`
- Modify: `src/engineering_office/ui/app.js`
- Modify: `src/engineering_office/ui/app.css`
- Test: `tests/test_friendly_control_room.py`
- Test: `tests/test_control_room_visual_polish.py`
- Test: `tests/test_living_office_accessibility.py`

**Interfaces:**
- Consumes: Task 9 APIs plus existing `/api/events`, `/api/replay`, terminal and floor endpoints.
- Default view shows project, LOCAL ONLY, mode/objective/status, real stage progress, total/stage timers, ETA learning/range, Needs You, friendly activity, and living floor.
- Advanced tabs remain `Activity, Terminal, Files, Messages, Task, Evidence, Traces, Model`.

- [ ] **Step 1: Write failing static/behavior tests** for simplified default hierarchy, friendly event descriptions, timers, ETA states, Needs You empty/action cards, model-loading explanation, report actions, advanced terminal access, larger-character hooks, and reduced motion.
- [ ] **Step 2: Run** `pytest -q tests/test_friendly_control_room.py tests/test_control_room_visual_polish.py tests/test_living_office_accessibility.py` **and confirm RED**.
- [ ] **Step 3: Implement** the UI using current event-driven Canvas floor; do not fabricate stage percentages or model-load percentages.
- [ ] **Step 4: Run** `pytest -q tests/test_friendly_control_room.py tests/test_control_room_visual_polish.py tests/test_living_office_accessibility.py tests/test_runtime_terminal_ui.py tests/test_living_floor_behavior.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `feat: simplify control room and expose run timing`.

### Task 11: CLI Run Modes, Reports, Index, Benchmarks, and Operator Docs

**Files:**
- Modify: `src/engineering_office/cli.py`
- Modify: `src/engineering_office/config.py`
- Create: `docs/FAST_AUDIT.md`
- Create: `docs/RUNTIME_OPTIMIZATION.md`
- Modify: `docs/CONTROL_ROOM.md`
- Modify: `README.md`
- Test: `tests/test_fast_audit_cli.py`

**Interfaces:**
- Adds/extends CLI following current argparse style: `office run ... --mode {fast-audit,check-report,fix,complete,custom}`, `office report`, `office index status|rebuild`, `office benchmark residency`, `office benchmark speculative qwen`, `office benchmark nemotron-runtime`.
- Documents that real runtime benchmarks must run on the target laptop and that unsupported challengers fall back to llama.cpp.

- [ ] **Step 1: Write failing CLI/config tests** for run modes, report lookup, index commands, benchmark commands, safe defaults, and backward-compatible config loading.
- [ ] **Step 2: Run** `pytest -q tests/test_fast_audit_cli.py` **and confirm RED**.
- [ ] **Step 3: Implement** CLI/config wiring and operator documentation, including FactoryMate A/B benchmark instructions but no fabricated timing claims.
- [ ] **Step 4: Run** `pytest -q tests/test_fast_audit_cli.py tests/test_cli_demo.py tests/test_ui_cli.py` **and confirm GREEN**.
- [ ] **Step 5: Commit** `docs: add fast audit and runtime optimization operations`.

### Task 12: Full Regression, Extracted-Release Smoke Test, and Artifact Build

**Files:**
- Modify: `tests/test_living_office_release.py`
- Create/Modify: `tests/test_fast_audit_release.py`
- Modify: `CHANGELOG.md`
- Output: `/mnt/data/autonomous-ai-engineering-office-complete.zip`

**Interfaces:**
- Consumes every previous task; produces release evidence and the clean ZIP only after verification.

- [ ] **Step 1: Add failing release tests** for deterministic Fast Audit fixture, second-run cache reuse, blocked-report generation, run/timing/report/index APIs, audit-mode immutability, selected benchmark fallback, and packaged friendly UI assets.
- [ ] **Step 2: Run release tests and confirm RED**, then implement only missing release wiring.
- [ ] **Step 3: Run complete test collection once, partition any slow nested suites into non-overlapping groups if the execution window requires it, and account for every collected test exactly once.**
- [ ] **Step 4: Run** `python -m compileall -q src`, `git diff --check`, and build the wheel from the exact committed tree.
- [ ] **Step 5: Create a clean source ZIP** excluding `.git`, `.office`, caches, worktrees, bytecode, test artifacts, and executor scratch; include the built wheel and release docs/assets.
- [ ] **Step 6: Extract the ZIP into a fresh directory/venv and verify:** wheel install, `office doctor`, offline demo, loopback-only Control Room, first Fast Audit, unchanged second audit with index/cache reuse, blocked report, APIs, terminal, replay, and verifier semantics.
- [ ] **Step 7: Record SHA-256 and commit** `release: fast audit and user-friendly control room` before handing off the artifact.

## Self-Review Result

- **Spec coverage:** All 13 rollout items in the approved spec map to Tasks 1–12; optional runtime technologies are benchmark-gated rather than required dependencies.
- **Interface consistency:** Run IDs flow from Task 1 through index/audit/report/ETA/UI; scheduler family labels match the residency/benchmark family names `qwen`, `nemotron`, `none`.
- **Safety:** Audit mutation policy is enforced at the existing tool authorization boundary; verifier semantics are explicitly regression-tested in Tasks 3, 9, and 12.
- **Review Focus:** Every listed failure mode has an explicit owning task/test.
- **Proportion:** The plan defines interfaces, tests, and acceptance commands without transcribing implementation bodies.
