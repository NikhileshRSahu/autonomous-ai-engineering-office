# Complete Feature Matrix

This document maps the approved Autonomous AI Engineering Office concept to implementation artifacts. "Adapter" means the core interface is implemented but a project-specific external program/service must be supplied; the Office does not fabricate that dependency.

| Concept | Implementation | Verification |
|---|---|---|
| General project + objective intake | `OfficeEngine.start`, legacy `ProjectIntake`, CLI `start/intake` | `test_office_engine.py`, `test_release_gaps.py` |
| Universal folder/archive/file/paste/Git/new intake | `UniversalIntakeService`, `IntakeSessionManager`, Control Room intake APIs | `test_universal_intake.py`, `test_intake_sessions.py`, `test_intake_api.py`, `test_intake_service.py` |
| Intake traversal/link/special-file/size defenses | safe ZIP/TAR extractors + upload path/limit guards | universal-intake security tests |
| Universal Control Room intake + New Floor | `ui/index.html`, `ui/app.js`, `DashboardService` | `test_universal_intake_static.py`, control-room/static tests |
| Native desktop intake pickers | Electron preload + IPC handlers | `test_desktop_shell.py` |
| Project discovery | `discovery.ProjectDiscovery` | `test_discovery_agents.py`, release-gap discovery tests |
| README/docs/manifests/tests/CI/git evidence | `ProjectDiscovery.inspect/_sample_text/_git_metadata` | release-gap discovery tests |
| Domain-independent staffing | `CapabilityRegistry`, `AgentFactory` | discovery + release-gap tests |
| Software specialists | capability JSON + role mapping | discovery/staffing tests |
| Mechanical/electronics/research specialists | capability JSON + discovery signals | release-gap tests |
| Temporary specialist creation | `AgentFactory.create_specialist` | agentic tool-loop tests |
| Specialist escalation | `OfficeEngine._resolve_specialist_requests` | `test_agentic_tool_loop.py` |
| Research requests | `ResearchManager`, provider protocol | agentic tool-loop tests |
| Honest no-provider BLOCKED | `ResearchManager(None)` path | agentic tool-loop tests |
| Project manager / task contracts | `TaskContract`, `ProjectPlan` | planning/model tests |
| Model-generated specialist DAG | `ModelPlanGenerator`, CLI `plan-model`, `start --plan-with-model` | `test_model_planning.py`, release-gap parser test |
| Dependency scheduling | `Scheduler.ready_tasks` | planning tests |
| Safe parallel task batches | `OfficeEngine.run`, `ThreadPoolExecutor` | `test_parallel_office.py` |
| Overlapping write-lock prevention | `WriteLockManager` | planning tests |
| Optional isolated Git worktrees | `GitWorkspaceManager` | release-gap worktree test |
| Structured agent contracts | `AgentSpec`, `AgentReport`, `Hypothesis`, `ToolAction` | model/storage/runtime tests |
| Strict JSON model output | `AgentRuntime` | runtime malformed-output tests |
| Multi-turn inspect→reason→modify loop | `AgentRuntime.propose`, Office iteration context | agentic tool-loop tests |
| Observation vs interpretation separation | report schema/prompt validation | runtime tests |
| Hypothesis contracts | `models.Hypothesis` + prompts | runtime tests |
| File read/search | `FileReadTool`, `FileSearchTool` | tool tests |
| File write/replace | `FileWriteTool`, `ReplaceTextTool` | tool tests |
| Shell/Git tools | `ShellTool`, `GitTool` | tool/security tests |
| Project-root confinement | `PathGuard` | traversal/symlink tests |
| Protect `.office` and `.git` | `PathGuard.PROTECTED_WRITE_ROOTS` | release-gap test |
| Command risk classification | `security.classify_command` | security tests |
| Persisted approval workflow | `ApprovalManager`, CLI approvals/approve/deny | governance/control/release tests |
| Pause/resume/stop | `OfficeControl`, Office + CLI | control/release tests |
| Objective change | `OfficeEngine.update_objective`, CLI `objective` | control/release tests |
| Agent replacement | `OfficeEngine.replace_agent`, CLI `replace-agent` | control tests |
| Evidence hashing | `EvidenceStore` | evidence tests |
| Secret redaction | `redact_secrets` | evidence tests |
| Structured audit events | `OfficeStore.add_event` + tool callbacks | tool/storage tests |
| Evidence Analyst | `feedback.EvidenceAnalyst` | feedback tests |
| Domain Reviewer | `feedback.DomainReviewer` | feedback tests |
| Adversarial Critic | `feedback.AdversarialCritic` | feedback tests |
| Bounded feedback loop | `FeedbackLoop` + `max_feedback_cycles` | feedback/release tests |
| Immutable acceptance snapshot | `AcceptanceSnapshot` | verification tests |
| Command-based gates | `Verifier` | verification tests |
| Required output/evidence | `AcceptanceSpec`, `Verifier` | verification tests |
| Independent PASS/FAIL/BLOCKED | `VerificationReport` + `Verifier` | verification tests |
| Prevent gate/test masking | Critic + protected internal paths + acceptance hash | feedback/security/verification tests |
| Failed-attempt memory | `OfficeEngine` → `MemoryManager.record_pattern` | release-gap test |
| Verified-success promotion only | `MemoryManager.promote_success` | evidence/memory tests |
| Agent performance metrics | `OfficeStore` + `MemoryManager.agent_performance` | memory/governance tests |
| Strength/weakness tags | memory skill APIs | release-gap test |
| Performance-based model escalation | `effective_complexity` | governance tests |
| Model tiers LOW/MEDIUM/HIGH/ESCALATION | `ModelRouter` | model-runtime tests |
| OpenAI-compatible local/remote models | `OpenAICompatibleProvider` | model-runtime HTTP payload test |
| Offline deterministic model | `ScriptedProvider` | demo/runtime tests |
| External agent CLI integration | `ExternalCommandAgentLauncher` | integration path documented |
| Generic external tool adapter | `CommandToolAdapter`, `ExtensionRegistry` | release-gap test |
| Persistent structured messages | `CommunicationManager`, SQLite messages | governance tests |
| Meeting/chatter limit | Director intervention in `CommunicationManager` | governance tests |
| Decision log | `DecisionLog` | governance tests |
| Benchmark aggregation | `BenchmarkSuite` | benchmark tests |
| Heterogeneous benchmark catalog | `BenchmarkCatalog`, example catalog | release-gap test |
| Verified autonomous completion metric | benchmark summary | benchmark tests |
| False PASS metric | benchmark summary | benchmark tests |
| Complete delivery guard | `DeliveryManager` | office + release-gap tests |
| Critical-risk delivery block | `DeliveryManager.create` | release-gap test |
| Architecture/change/evidence/repro bundle | `DeliveryManager` | release-gap test |
| DELIVERED project state | `OfficeEngine.deliver` | release-gap test |
| Safe ZIP extraction | `ProjectIntake` | release-gap tests |
| ZIP-slip/symlink/size protections | `ProjectIntake` | release-gap tests |
| Configuration via JSON/env | `OfficeConfig`, model profiles | model/config tests + examples |
| CLI operator surface | `cli.py` | CLI/demo/release tests |
| Offline end-to-end proof | CLI `demo` | `test_cli_demo.py` |
| Replaceable orchestration/model layers | provider/launcher/adapter interfaces | architecture + extension docs |
| Multi-project floor registry | `FloorRegistry`, Control Room floor selector | `test_control_room_service.py`, `test_control_room_server.py` |
| Living engineering office floor | V2 `ui/index.html`, `ui/app.css`, `ui/app.js` | `test_control_room_static.py` + browser render |
| Persistent agent process/role roster | V2 Control Room roster | static + interaction render tests |
| Selected-agent inspector | `DashboardService.agent_detail` | `test_control_room_service.py` |
| Agent terminal/execution reconstruction | `DashboardService._terminal_lines`, preserved action args/reasons | service + `test_agent_runtime.py` |
| Agent files/messages/task/evidence/traces tabs | Control Room inspector + service detail payload | service/static tests |
| Durable per-agent queue | `CommunicationManager` + inspector queue | control-room service tests |
| Operational agent steering | `OfficeEngine.steer_agent` + message injection into `AgentRuntime` context | `test_agent_controls.py` |
| Per-agent pause/halt/resume | `AgentControlManager`, scheduler enforcement | `test_agent_controls.py` |
| Dynamic Add Agent from Control Room | `OfficeEngine.add_agent`, `/api/add-agent` | server/service tests |
| Visible feedback/verification states | V2 state mapping/CSS | `test_control_room_static.py` + browser render |
| Optional native Electron shell | `desktop/main.js`, `desktop/preload.js` | `test_desktop_shell.py`, `node --check` |
| Desktop shell loopback/navigation isolation | Electron local-origin guards | `test_desktop_shell.py` |

## External capability boundary

The following are intentionally adapters rather than fake built-ins: CAD/EDA solvers, browser automation, cloud/provider accounts, production databases, robotics hardware/simulators, proprietary engineering software and web research. Register those capabilities with `CommandToolAdapter`, external agent launchers, or a `ResearchProvider`; then grant only the necessary specialist scopes/tools.
