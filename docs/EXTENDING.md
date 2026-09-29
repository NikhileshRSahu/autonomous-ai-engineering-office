# Extending the Office

## Add or modify a capability

Edit `src/engineering_office/data/capabilities.json`. Each capability defines default tool names and write scopes. Add discovery signals in `ProjectDiscovery` or map specialist-request keywords in `AgentFactory` when automatic detection is useful.

Never give a capability broader write scope merely because the model is capable of discussing that domain.

## Add a native tool

Implement a tool with a stable `name` and `execute(args) -> ToolResult`. Enforce project-root safety, least-privilege scopes, timeouts, fail-closed validation and audit callbacks for mutation. Register it in the task's `ToolRegistry` only when the specialist contract allows that tool.

## Add an external project-specific tool

`CommandToolAdapter` accepts an argv list (never shell interpolation), sends JSON on stdin, and returns stdout/stderr/return code. Register adapters in `ExtensionRegistry`.

This is the intended bridge for CAD/EDA helpers, browser automation, database tooling, containers/build systems, robot/simulator commands, or proprietary engineering programs.

## Add an external engineering-agent CLI

Use `ExternalCommandAgentLauncher` with a command template containing `{project}` and `{prompt}`. This allows OpenCode/Munder/Codex-like CLIs to be launched without making the Office depend on them.

## Add research/search

Implement `ResearchProvider.research(ResearchRequest)` or use `CommandResearchProvider` for a helper that accepts JSON on stdin and returns JSON findings. Findings must include sources/confidence/applicability/limitations. With no provider, research requests return BLOCKED honestly.

## Add model endpoints

Use an OpenAI-compatible endpoint in model configuration. Keep API keys in environment variables via `api_key_env`.

## Add acceptance gates

Place `acceptance.json` at the project root before `office start`, or edit the copied `.office/acceptance/project.json` before execution begins. Candidate tools cannot modify `.office` during a task. Typical gates include unit/integration tests, linters, build commands, simulations, benchmarks, static analysis, or project-specific validation scripts.

## Add a benchmark family

Create a benchmark catalog JSON matching `BenchmarkCatalog`. Record actual run outcomes as `BenchmarkResult`, then aggregate with `office benchmark --input results.json`.
