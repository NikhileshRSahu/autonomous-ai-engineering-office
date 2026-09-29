# Architecture

The Office is a domain-independent engineering runtime. It separates **management**, **specialist reasoning**, **tool execution**, **evidence**, **critique**, and **verification** so a model cannot simply declare its own work correct.

## Core flow

```text
Project + Objective
  -> Discovery
  -> Dynamic Staffing
  -> Project Plan / DAG
  -> Specialist Proposal
  -> Evidence Analyst
  -> Domain Review
  -> Adversarial Critic
  -> Authorized Tool Execution
  -> Test / Measurement
  -> Independent Verifier
  -> PASS | Evidence-fed Retry | BLOCKED
  -> Verified Memory
  -> Delivery
```

## Boundaries

- `models.py`: immutable vocabulary and contracts.
- `storage.py`: SQLite system of record.
- `discovery.py`: evidence-based project mapping.
- `capabilities.py` + `agent_factory.py`: dynamic staffing.
- `planning.py` + `scheduler.py`: DAG validation and safe write concurrency primitives.
- `security.py` + `tools.py`: root-scoped execution and risk gates.
- `models_runtime.py`: local/remote OpenAI-compatible inference plus deterministic providers.
- `agent_runtime.py`: strict JSON proposal/action protocol.
- `feedback.py`: Evidence Analyst, Domain Reviewer, Adversarial Critic.
- `verification.py`: immutable acceptance snapshots and independent PASS/FAIL/BLOCKED.
- `evidence.py` + `memory.py`: hashed artifacts and verified organizational memory.
- `research.py`: explicit configurable research provider; never fakes research.
- `office.py`: Director/orchestrator.
- `delivery.py`: verified delivery bundle.
- `benchmark.py`: reliability metrics including false-PASS rate.

## Dynamic agents

Generated agents receive a mission, capability set, allowed tools, read/write scopes, forbidden actions and model tier. Temporary specialists may be created for narrower problems. A title alone does not create expertise; the role must be paired with appropriate references/tools and verification.

## Model independence

Logical agents share configured endpoints. The core can route LOW/MEDIUM/HIGH/ESCALATION tasks to different models. It does not require Munder Difflin, OpenCode, Claude, Codex, Nemotron or any specific model. External CLIs can be wrapped through `ExternalCommandAgentLauncher`.
