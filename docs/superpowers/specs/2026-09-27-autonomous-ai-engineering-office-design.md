# Autonomous AI Engineering Office — Design Specification

## 1. Mission
Build a domain-independent AI engineering office that accepts an arbitrary project plus an objective, understands the project, researches unknowns, dynamically staffs specialists, plans dependency-aware work, executes through controlled tools, records evidence, challenges its own reasoning, independently verifies acceptance criteria, learns from verified outcomes, and delivers a reproducible project package.

## 2. Non-negotiable operating principles
1. Evidence outranks confidence.
2. Tests and measurements outrank agent consensus.
3. No implementation agent may verify its own work.
4. Specialists remain inside explicit authority and write scopes.
5. Agents may request new specialists when a problem crosses domains.
6. Failed hypotheses and failed fixes are retained as organizational memory.
7. Acceptance gates cannot be weakened to manufacture PASS.
8. Parallel work is permitted only when dependencies and write scopes do not conflict.
9. Model strength is routed by task complexity; expensive/deep models are escalation resources.
10. Irreversible/high-risk external actions require explicit approval.
11. Uncertain technical knowledge triggers research rather than confident guessing.
12. Project state, evidence, decisions and memory are stored structurally, not only in chat.
13. Every important fix needs reproducible evidence.
14. The office learns only from verified outcomes.
15. False PASS is treated as more serious than an admitted failure or BLOCKED state.

## 3. System lifecycle
`UNDERSTAND → RESEARCH → STAFF → PLAN → EXECUTE → OBSERVE → HYPOTHESIZE → TEST → REVIEW → VERIFY → INTEGRATE/REDO → DELIVER`.

Project states: `NEW_PROJECT, DISCOVERING, PROJECT_MAPPED, STAFFING, PLANNING, EXECUTING, REVIEWING, VERIFYING, PASS, FAIL, BLOCKED, DELIVERED`.

Task states: `NEW, TRIAGED, ASSIGNED, EVIDENCE_REQUIRED, HYPOTHESIS, EXPERIMENT, IMPLEMENTATION, REVIEW, TEST, VERIFY, PASS, FAILED, BLOCKED, NEEDS_RESEARCH, NEEDS_SPECIALIST, REGRESSION_FAILED, ESCALATED`.

## 4. Permanent office roles
- **Office Director**: owns project orchestration, staffing, escalation, conflict resolution and scope control. Does not self-verify.
- **Project Discovery Agent**: maps stack, code, docs, tests, current failures, constraints, unknowns and required domains.
- **Project Manager**: turns project map into dependency-aware tasks, enforces write locks and concurrency rules.
- **Agent Factory**: composes temporary specialists from capabilities, context, tools and permissions.
- **Research Lead**: answers uncertain technical questions from authoritative sources through configurable research tools/providers.
- **Evidence Analyst**: read-mostly analyst separating observations from interpretations and identifying missing measurements.
- **Adversarial Critic**: attacks assumptions, alternative explanations, benchmark manipulation and symptom-masking fixes.
- **QA/Test Executor**: runs reproducible tests/benchmarks and captures outputs.
- **Independent Verifier**: sole role allowed to emit PASS for a task/project; cannot implement candidate fixes.
- **Memory Manager**: stores verified patterns, failures, agent performance, research and decisions.

## 5. Dynamic specialist system
Specialists are not predeclared per project. The office discovers required expertise and creates temporary agents from reusable capabilities such as software engineering, systems, research, math, statistics, ML, simulation, robotics, controls, electronics, mechanical, database, security, networking, cloud, frontend, backend, UX, testing, DevOps, documentation, benchmarking and optimization.

Each generated specialist has: name, mission, capabilities, allowed tools, read scopes, write scopes, forbidden actions, model tier, required output contract, review requirements and lifecycle (`CREATE → BRIEF → WORK → SUBMIT → REVIEW → HANDOFF → ARCHIVE`).

A specialist can issue `REQUEST_SPECIALIST` with required expertise, evidence, reason, expected contribution and urgency. The Director may approve it and Agent Factory creates a narrower specialist.

## 6. Project intake and discovery
Input can be a local repository/folder, extracted ZIP, or new workspace plus objective. Discovery must inspect at least repository tree, README/docs, dependencies/manifests, build scripts, tests, CI, configuration and relevant git metadata. It detects languages/frameworks using file evidence, records unknowns, assesses risk and emits a `ProjectMap`.

## 7. Planning and scheduling
Every task has a contract: ID, owner, goal, inputs, dependencies, allowed write scope, required evidence, acceptance criteria, risk level, complexity and prohibited actions. Project Manager stores a DAG, detects cycles, returns ready tasks, schedules non-conflicting tasks concurrently and prevents overlapping write scopes. Significant implementation work should happen on isolated git branches/worktrees when available.

## 8. Tool layer and permissions
Core tools: filesystem read/search/write/replace, repository inspection, git, shell, Python/test execution, HTTP/research adapters, database adapter interface, browser/automation adapter interface, container/build adapter interface and extension registry.

Tools enforce project-root path safety, read/write scopes, command risk classification and approval requirements. Destructive commands, pushes/publishes/deploys, credential mutations, production database writes, financial or irreversible actions are blocked unless an explicit approval policy grants them.

## 9. Model layer
Support OpenAI-compatible HTTP endpoints without SDK dependency plus deterministic/offline providers for testing. A model router maps `LOW, MEDIUM, HIGH, ESCALATION` task complexity to named model profiles. Multiple logical agents share model servers; one model instance per role is not required. The system must work in dry-run/demo mode without any external model.

## 10. Agent execution protocol
Agent inputs: role contract, project summary, task contract, relevant files/evidence/memory/research, tool catalog and immutable rules. Agent output is structured JSON containing observations, hypotheses, confidence, alternatives, requested evidence, proposed actions, tests, risks, specialist/research requests and handoff.

Agents must separate observations from interpretations. Complex debugging must use hypothesis contracts with evidence-for, evidence-against, alternatives, confidence, discriminating test and predicted outcomes. Agents should prefer a minimum discriminating experiment before broad edits.

## 11. Feedback layer
Every substantive candidate follows:
`Builder/Specialist → Evidence Analyst → Domain Reviewer (when applicable) → Adversarial Critic → Test Executor → Independent Verifier`.

Reviewer/critic results are `APPROVE_FOR_IMPLEMENTATION`, `REJECT_HYPOTHESIS`, or `MORE_EVIDENCE_REQUIRED`. Agent consensus never counts as proof. The system limits unproductive conversational loops; exchanges must terminate in an action, experiment, evidence request, specialist request, implementation or BLOCKED.

## 12. Evidence system
Each project stores immutable-ish evidence artifacts with metadata and SHA-256 hashes: logs, test output, traces, metrics, screenshots/videos, benchmark outputs, diffs, model reports and summaries. Evidence is organized by ticket/task/run. Machine-readable results are preferred. Audit events record important transitions and tool actions.

## 13. Acceptance and verification
Acceptance criteria live separately from implementation. At verification start, acceptance files are snapshotted by content hash. Candidate workers cannot alter gates during a task. The verifier executes command-based gates, checks exit codes and optional required output, compares immutable hashes, checks required evidence and emits only `PASS`, `FAIL` or `BLOCKED` with evidence references.

Automatic verification invalidators include disabled tests, weakened thresholds, cherry-picked seeds, hidden failed trials, hardcoded expected outputs, removed safety checks or candidate modifications to acceptance gates without authorized requirement change.

## 14. Organizational memory
Persistent SQLite/JSON-backed memory stores projects, tasks, decisions, verified failure patterns, successful fixes, rejected approaches, research, evidence metadata, agent performance and benchmark results. Only verified outcomes can be promoted into reusable `successful_fix` memory. Agent performance tracks verified success, false-PASS rate, average iterations, strength/weakness tags and can influence staffing/model routing.

## 15. Research department
Research is provider-based. A research request records topic, questions, freshness, preferred source classes and reason. Providers may be web APIs, browser agents or manual/connected services. Results store finding, source, confidence, applicability, limitations and implementation notes. The core must not pretend web research succeeded if no provider is configured.

## 16. Communication and meetings
Agent-to-agent messages are structured and persisted. Long free-form meetings are discouraged. After a configurable number of non-actionable exchanges, Director intervenes and forces action/evidence/blocking resolution.

## 17. Delivery
A project can be delivered only when required tasks are terminal, acceptance/regression gates pass, critical risks are addressed, documentation/deliverables exist and verifier approves. Delivery package includes final project pointer/copy policy, acceptance report, test report, change summary, architecture summary, unresolved risks, evidence summary and reproducibility instructions.

## 18. CLI
Provide an `office` CLI with at least: `init`, `doctor`, `inspect`, `staff`, `plan`, `run`, `status`, `verify`, `memory`, `benchmark`, `demo`, and `deliver`. `office start PATH --objective "..."` performs intake + discovery + staffing + planning. `run` defaults to safe local operation; `--auto` still respects high-risk approval gates.

## 19. Configuration
Project-local `.office/` stores state, SQLite DB, evidence, acceptance, generated agents, research, runs and delivery. User/global model profiles may be provided through JSON and environment variables; secrets are never written into generated project state by default.

## 20. Integrations
Core orchestration must not depend on Munder Difflin or OpenCode. Provide adapters/documentation so external agent CLIs can be launched through command templates and local OpenAI-compatible model servers can be used. This preserves replaceability.

## 21. Offline proof/demo
Ship a deterministic seeded broken Python project and a scripted offline model/provider. `office demo` must exercise the real lifecycle: discover project, create appropriate specialist, plan a task, observe failing test, propose an edit action, apply through tool permission layer, run critic/review, verify immutable acceptance gate, store evidence/memory/audit, and report PASS. The demo proves orchestration, not general model intelligence.

## 22. Benchmarks
Provide a benchmark harness and fixtures/schema for heterogeneous seeded faults. Required metrics include project understanding, specialist selection, root-cause accuracy when known, verified repair rate, false-PASS rate, regression rate, human interventions, iterations, elapsed time and model/token accounting when available. Primary metric: Verified Autonomous Task Completion Rate. Critical reliability metric: False PASS Rate, target 0.

## 23. Security/reliability constraints
- Never escape the project root via file tools.
- Never execute high-risk commands without approval.
- Never persist secrets in logs/evidence when detectable; redact common key/token formats.
- Use bounded retries/iterations.
- Validate structured model output before acting.
- Record every mutating tool action in audit log.
- Fail closed on malformed permissions, unknown tool actions, acceptance hash mismatches and missing required evidence.

## 24. Required quality bar
The repository must include packaging metadata, type-annotated Python, tests, an offline end-to-end demo, sample configuration, architecture/docs, extension guide, security model, benchmark guide, and reproducible verification commands. The final ZIP must exclude caches, worktrees, model weights, secrets and transient runtime state.
