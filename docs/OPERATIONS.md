# Operations

## Install and health check

```bash
python -m pip install -e .
office doctor .
```

## Offline proof

```bash
office demo --workspace /tmp/office-demo
```

## Universal intake

The recommended operator path is the Control Room. Start it from any existing local directory and choose **New Floor** or the startup intake panel:

```bash
office ui /path/to/local/directory --app
```

Accepted sources:

- existing local folder;
- ZIP/TAR-family archive by path, picker, or browser upload;
- one or many local files;
- browser-selected folder tree;
- pasted code/text (one or many named snippets);
- Git repository;
- a brand-new project from a name/objective.

Directories are opened in place. Other sources are normalized under `~/.engineering-office/workspaces/<slug>-<id>/` by default. Browser uploads are streamed into bounded staging sessions under `~/.engineering-office/staging/`; cancel/commit removes staging, and stale sessions expire after 24 hours by default.

Intake only materializes the project. It does **not** execute project code or automatically mark the project correct. After normalization, Project Discovery and the Director operate through the normal Office start/run/verify flow.

Legacy commands remain supported:

```bash
office inspect /path/to/project --objective "understand and complete"
office intake project.zip /tmp/project-workspace --zip
```

If intake fails, the current floor remains unchanged. The UI reports a stable error code/message (for example `ARCHIVE_UNSAFE`, `LIMIT_EXCEEDED`, `GIT_CLONE_FAILED`, or `BACKEND_UNREACHABLE`) instead of replacing the form with a generic network error.

## Start

Fallback deterministic plan:

```bash
office start /path/to/project --objective "Complete and production-harden this project"
```

Model-generated multi-specialist DAG:

```bash
office start /path/to/project \
  --objective "Complete and production-harden this project" \
  --config /path/to/model_profiles.json \
  --plan-with-model
```

Review `.office/acceptance/project.json`. If no safe acceptance gate can be inferred, the Office intentionally creates a failing/unconfigured gate rather than inventing success.

## Run

```bash
office run /path/to/project --config /path/to/model_profiles.json --auto
```

Optional runtime overrides:

```bash
office run PROJECT --config MODELS.json --max-iterations 8 --parallelism 4 --auto
```

`--auto` does not bypass high-risk approval gates.

## Governance

```bash
office pause PROJECT
office resume PROJECT
office resume PROJECT --reset-blocked
office stop PROJECT

office approvals PROJECT
office approve PROJECT APR-...
office deny PROJECT APR-...

office objective PROJECT --set "new objective"
office replace-agent PROJECT --old "Old Agent" --expertise "new specialty"
```

A task blocked for approval can be resumed after approval with `--reset-blocked`.

## Re-plan explicitly

```bash
office plan-model PROJECT --config MODELS.json --tier HIGH
```

## Inspect state

```bash
office status PROJECT
office plan PROJECT
office memory PROJECT
office verify PROJECT
```

## Delivery

```bash
office deliver PROJECT
```

Delivery requires project PASS + every task PASS + independent verification. The generated `.office/delivery/` includes manifest, acceptance/test/evidence reports, architecture, changes, unresolved-risks report, reproducibility instructions and project pointer policy.

## Test this repository

Fast foundational group:

```bash
python -m pytest -q \
  tests/test_models_storage.py tests/test_discovery_agents.py \
  tests/test_planning_scheduler.py tests/test_tools_security.py \
  tests/test_evidence_memory.py tests/test_model_runtime.py \
  tests/test_agent_runtime.py tests/test_feedback.py tests/test_verification.py
```

Governance/planning/CLI group:

```bash
python -m pytest -q \
  tests/test_governance.py tests/test_model_planning.py \
  tests/test_office_controls.py tests/test_parallel_office.py \
  tests/test_benchmark.py tests/test_cli_demo.py tests/test_release_gaps.py \
  tests/test_ui_service.py tests/test_ui_server.py tests/test_ui_cli.py
```

Nested acceptance/process group:

```bash
python -m pytest -q tests/test_agentic_tool_loop.py tests/test_office_engine.py
```

The last group is slower because the Office intentionally starts subprocess acceptance suites inside temporary projects.
