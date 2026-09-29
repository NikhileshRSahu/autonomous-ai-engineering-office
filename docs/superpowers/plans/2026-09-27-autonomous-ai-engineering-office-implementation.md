# Autonomous AI Engineering Office Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable, domain-independent AI engineering office with dynamic staffing, controlled tools, feedback/critic/verifier loops, evidence and memory, model routing, CLI, offline demo, benchmarks, and delivery packaging.

**Architecture:** A Python package (`engineering_office`) owns domain models, SQLite state, discovery, capability/staffing, DAG planning, scoped tools, model providers/router, agent runtime, feedback, verification, evidence/memory, orchestration and CLI. Project-local `.office/` stores durable state. The core is model/provider-agnostic and includes an offline deterministic provider proving the end-to-end lifecycle.

**Tech Stack:** Python 3.11+ standard library, SQLite, `argparse`, `urllib`, `subprocess`, `concurrent.futures`; pytest for tests; JSON configuration/state; optional external OpenAI-compatible endpoints and command-based integrations.

**Spec:** `docs/superpowers/specs/2026-09-27-autonomous-ai-engineering-office-design.md`

## Global Constraints
- Domain-independent; no project-specific logic in core orchestration.
- False PASS prevention and independent verification are mandatory.
- Candidate agents cannot weaken acceptance gates.
- File tools must stay inside project root and obey scopes.
- High-risk commands fail closed without explicit approval.
- Structured model output is validated before tool execution.
- Runtime works offline in demo/test mode.
- No external SDK dependency is required.
- Final ZIP excludes caches, worktrees, secrets, model weights, and runtime state.

## Review Focus
1. Path traversal/symlink escape must be rejected by file tools — Task 4 tests both `..` and symlink escape.
2. Acceptance file mutation after snapshot must force verification failure — Task 9 test.
3. Cyclic dependency graphs must be rejected deterministically — Task 3 test.
4. Malformed model JSON/tool actions must fail closed without mutation — Task 7 test.
5. High-risk shell commands must require approval even in auto mode — Task 4 test.

---

### Task 1: Package scaffold, domain models, and durable state

**Files:**
- Create: `pyproject.toml`, `README.md`, `src/engineering_office/__init__.py`, `src/engineering_office/models.py`, `src/engineering_office/storage.py`, `tests/test_models_storage.py`

**Interfaces:**
- Produces: enums/data classes `ProjectState`, `TaskState`, `Complexity`, `RiskLevel`, `Verdict`, `ProjectMap`, `AgentSpec`, `TaskContract`, `AgentReport`; `OfficeStore(path)` CRUD for projects/tasks/events/messages/memory/agent metrics.

- [ ] Write failing round-trip/state-transition tests.
- [ ] Run tests and verify RED.
- [ ] Implement typed models, legal transition guards, SQLite schema/CRUD.
- [ ] Run task tests and whole suite; verify GREEN.
- [ ] Commit `feat: add office domain model and state store`.

### Task 2: Discovery, capabilities, and dynamic Agent Factory

**Files:**
- Create: `src/engineering_office/discovery.py`, `src/engineering_office/capabilities.py`, `src/engineering_office/agent_factory.py`, `src/engineering_office/data/capabilities.json`, `tests/test_discovery_agents.py`

**Interfaces:**
- Consumes: `ProjectMap`, `AgentSpec`.
- Produces: `ProjectDiscovery.inspect(root, objective) -> ProjectMap`; `CapabilityRegistry`; `AgentFactory.staff(project_map) -> list[AgentSpec]`, `AgentFactory.create_specialist(...)`.

- [ ] Write failing detection/staffing/specialist-request tests.
- [ ] Verify RED.
- [ ] Implement evidence-based stack detection, capability composition, minimal staffing and generated role contracts.
- [ ] Verify GREEN and commit `feat: add project discovery and dynamic staffing`.

### Task 3: Task planning, DAG scheduler, and write-lock manager

**Files:**
- Create: `src/engineering_office/planning.py`, `src/engineering_office/scheduler.py`, `tests/test_planning_scheduler.py`

**Interfaces:**
- Produces: `ProjectPlan(tasks)`, `PlanValidator`, `Scheduler.ready_tasks(...)`, `WriteLockManager.acquire/release`.

- [ ] Write failing DAG order, cycle rejection, dependency, and overlapping-write-scope tests.
- [ ] Verify RED.
- [ ] Implement planner primitives, safe ready-set scheduling and path-prefix write locks.
- [ ] Verify GREEN and commit `feat: add dependency scheduler and write locks`.

### Task 4: Scoped tool layer, risk policy, and audit hooks

**Files:**
- Create: `src/engineering_office/security.py`, `src/engineering_office/tools.py`, `tests/test_tools_security.py`

**Interfaces:**
- Produces: `PermissionSet`, `ApprovalPolicy`, `ToolRegistry`, `FileReadTool`, `FileSearchTool`, `FileWriteTool`, `ReplaceTextTool`, `ShellTool`, `GitTool`, `ToolResult`.

- [ ] Write failing traversal, symlink escape, write-scope, high-risk command and audit tests.
- [ ] Verify RED.
- [ ] Implement project-root resolution, scope enforcement, command classifier, approval gate, safe subprocess execution and mutating-action audit callbacks.
- [ ] Verify GREEN and commit `feat: add scoped tools and risk controls`.

### Task 5: Evidence, redaction, audit, and organizational memory

**Files:**
- Create: `src/engineering_office/evidence.py`, `src/engineering_office/memory.py`, `tests/test_evidence_memory.py`

**Interfaces:**
- Produces: `EvidenceStore.add_text/add_file`, SHA-256 metadata, secret redaction, `MemoryManager.record_*`, verified-pattern promotion and agent performance statistics.

- [ ] Write failing hash/redaction/promotion/performance tests.
- [ ] Verify RED.
- [ ] Implement evidence store and memory manager over `OfficeStore`.
- [ ] Verify GREEN and commit `feat: add evidence and organizational memory`.

### Task 6: Model providers and complexity router

**Files:**
- Create: `src/engineering_office/models_runtime.py`, `src/engineering_office/config.py`, `examples/model_profiles.json`, `tests/test_model_runtime.py`

**Interfaces:**
- Produces: `ModelProvider` protocol, `OpenAICompatibleProvider`, `ScriptedProvider`, `ModelProfile`, `ModelRouter.route(complexity)`.

- [ ] Write failing profile routing, offline scripted response, HTTP payload and missing-profile tests.
- [ ] Verify RED.
- [ ] Implement providers using `urllib`, env-secret lookup, usage metadata and fail-closed routing.
- [ ] Verify GREEN and commit `feat: add model providers and routing`.

### Task 7: Agent runtime and structured action protocol

**Files:**
- Create: `src/engineering_office/agent_runtime.py`, `src/engineering_office/prompts.py`, `tests/test_agent_runtime.py`

**Interfaces:**
- Produces: `AgentRuntime.run(agent, task, context) -> AgentReport`; strict JSON parser; action schema (`tool`, `args`, `reason`); specialist/research request extraction.

- [ ] Write failing valid/malformed JSON, unknown-tool, out-of-scope action and observation-vs-interpretation contract tests.
- [ ] Verify RED.
- [ ] Implement prompt assembly, report validation and controlled action dispatch.
- [ ] Verify GREEN and commit `feat: add structured agent execution`.

### Task 8: Feedback layer and bounded self-correction

**Files:**
- Create: `src/engineering_office/feedback.py`, `tests/test_feedback.py`

**Interfaces:**
- Produces: `EvidenceAnalyst`, `DomainReviewer`, `AdversarialCritic`, `FeedbackDecision`, `FeedbackLoop.evaluate(...)` with max-cycle guard.

- [ ] Write failing approve/reject/more-evidence, symptom-masking, no-evidence and loop-bound tests.
- [ ] Verify RED.
- [ ] Implement evidence-first feedback decisions and structured critique records.
- [ ] Verify GREEN and commit `feat: add adversarial feedback loop`.

### Task 9: Acceptance snapshots and independent verifier

**Files:**
- Create: `src/engineering_office/verification.py`, `tests/test_verification.py`

**Interfaces:**
- Produces: `AcceptanceSpec.load`, `AcceptanceSnapshot.capture/check_unchanged`, `Verifier.verify(...) -> VerificationReport`.

- [ ] Write failing pass/fail/block, gate mutation, missing evidence and required-output tests.
- [ ] Verify RED.
- [ ] Implement immutable hash checks, command gates and PASS/FAIL/BLOCKED logic.
- [ ] Verify GREEN and commit `feat: add independent acceptance verification`.

### Task 10: Office Director/orchestrator, staffing, planning, execution and delivery

**Files:**
- Create: `src/engineering_office/office.py`, `src/engineering_office/delivery.py`, `tests/test_office_engine.py`

**Interfaces:**
- Produces: `OfficeEngine.init/start/status/run/verify/deliver`, project-local `.office/` initialization, bounded iteration, task transitions, feedback-to-retry path and delivery manifest.

- [ ] Write failing lifecycle, blocked-risk, failed-verification retry, verified-memory promotion and delivery-guard tests.
- [ ] Verify RED.
- [ ] Implement orchestration by composing Tasks 1–9.
- [ ] Verify GREEN and commit `feat: add autonomous office orchestration`.

### Task 11: CLI, doctor, external launcher adapter, and offline end-to-end demo

**Files:**
- Create: `src/engineering_office/cli.py`, `src/engineering_office/integrations.py`, `examples/demo_project/*`, `tests/test_cli_demo.py`

**Interfaces:**
- Produces CLI `office init|doctor|inspect|staff|plan|start|run|status|verify|memory|benchmark|demo|deliver`; `ExternalCommandAgentLauncher`.

- [ ] Write failing CLI help/doctor/start/demo tests.
- [ ] Verify RED.
- [ ] Implement argparse CLI, demo project generator and scripted provider that fixes one seeded Python defect through the real action/feedback/verifier path.
- [ ] Verify GREEN and commit `feat: add CLI and offline office demo`.

### Task 12: Benchmark harness, documentation, sample configs, packaging and final verification

**Files:**
- Create: `src/engineering_office/benchmark.py`, `tests/test_benchmark.py`, `docs/ARCHITECTURE.md`, `docs/SECURITY.md`, `docs/EXTENDING.md`, `docs/MODELS.md`, `docs/BENCHMARKS.md`, `docs/OPERATIONS.md`, `examples/project_acceptance.json`, `examples/office_config.json`, `LICENSE`, `CHANGELOG.md`

**Interfaces:**
- Produces: benchmark result schema/aggregate metrics, complete operator/developer documentation and installable package.

- [ ] Write failing metric aggregation/false-PASS tests.
- [ ] Verify RED.
- [ ] Implement benchmark module and documentation/config examples.
- [ ] Run `pytest -q`, `python -m engineering_office.cli doctor`, and `python -m engineering_office.cli demo --workspace <temp>`.
- [ ] Build clean source ZIP excluding runtime/cache/worktree content.
- [ ] Commit `docs: complete engineering office release`.
