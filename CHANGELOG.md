# Changelog

## 0.1.0 — 2026-09-27
- Initial autonomous engineering office runtime.
- Dynamic project discovery and staffing.
- Scoped tools and approval controls.
- Evidence/feedback/independent verification loop.
- Local/remote OpenAI-compatible model routing.
- Organizational memory and agent metrics.
- CLI, offline end-to-end demo, benchmark schema and delivery bundle.
- User-friendly local Control Room UI with Office floor, tasks, activity, approvals, evidence, memory, model routing, delivery, settings, and app-window launch mode.
- Replaced the dashboard-first presentation with Control Room V2: living engineering floor, persistent agent roster, selected-agent inspector, queue/steer controls, and Terminal/Files/Messages/Task/Evidence/Traces tabs.
- Added multi-project floors, dynamic Add Agent, operational per-agent pause/halt/resume/steer, and execution transcript reconstruction.
- Added an optional hardened Electron desktop wrapper while keeping the Python Office engine as the single source of truth.

## Living Control Room visual pass

- Replaced generic workstation-only agents with original CSS pixel engineer sprites.
- Added state-driven movement between engineering, research, review, verification, and break zones.
- Added visible agent handoffs, attention bubbles, role-aware equipment, and activity summary.
- Reused agent identity in the roster and inspector without external assets.
- Added reduced-motion support while preserving all existing control-room workflows.

## 0.4.0 — 2026-09-28
- Added Fast Audit and Check & Report run modes with read-only enforcement, incremental SHA-256 indexing, Qwen batching, and permanent reports.
- Added User-Friendly Control Room with elapsed/stage timers, history-based ETA ranges, Needs You guidance, friendly activity summaries, report actions, and larger living-office characters.
- Added benchmark-aware model residency, vLLM/llama.cpp residency benchmarking, Qwen speculative-decoding challengers, and Nemotron runtime challenger benchmarking with safe llama.cpp fallback.
- Added durable run records, run timing APIs, report APIs, index status, and replay-linked run history.

## Hybrid Repair — 2026-09-28
- Repaired the broken Fast Audit completion path introduced by an automated patch and restored clean Python parsing.
- Preserved `AUDIT_COMPLETE_LIMITED` semantics when required AI analysis is unavailable instead of presenting a normal completed AI audit.
- Restored skipped/unavailable checks in reports and removed fabricated Qwen/Nemotron/provider claims.
- Added actual provider/model provenance to audit metrics and rendered reports.
- Enforced zero-cost eligibility for cloud providers; explicit paid OpenRouter models are rejected under zero-cost mode.
- Kept routine LOW/MEDIUM source analysis local by default; cloud escalation receives compact evidence only unless source-snippet upload is explicitly enabled.
- Distinguished configured providers from zero-cost-eligible providers in the Control Room and Needs You guidance.
- Added hybrid provider/privacy/provenance regression coverage; release suite now contains 331 passing tests.
