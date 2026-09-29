from __future__ import annotations

from pathlib import Path
from typing import Any
from html import escape
import json
import shutil

from .run_records import RunRecord
from .runtime_events import RuntimeEventStore


class RunReportBuilder:
    def __init__(self, project_root: str | Path):
        self.root = Path(project_root).resolve()

    def build(
        self,
        record: RunRecord,
        *,
        findings: list[dict[str, Any]],
        tests: list[dict[str, Any]],
        risks: list[dict[str, Any]],
        model_metrics: dict[str, Any],
        skipped: dict[str, str] | None = None,
        evidence_paths: list[str | Path] | None = None,
        index_status: dict[str, Any] | None = None,
    ) -> Path:
        target = self.root / ".office" / "reports" / record.run_id
        evidence_dir = target / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        record.report_dir = str(target)
        skipped = dict(skipped or {})
        metadata = record.to_dict() | {"status": record.status, "index_status": index_status or {}, "skipped": skipped}
        self._json(target / "run-metadata.json", metadata)
        self._json(target / "findings.json", findings)
        self._json(target / "test-results.json", tests)
        self._json(target / "risks.json", risks)
        self._json(target / "model-performance.json", model_metrics)
        self._timeline(target / "timeline.jsonl", record)
        copied = []
        for raw in evidence_paths or []:
            source = Path(raw)
            if source.is_file():
                dest = evidence_dir / source.name
                n = 2
                while dest.exists():
                    dest = evidence_dir / f"{source.stem}-{n}{source.suffix}"; n += 1
                shutil.copy2(source, dest); copied.append(dest.name)
        report = self._markdown(record, findings, tests, risks, skipped, copied, model_metrics)
        (target / "REPORT.md").write_text(report, encoding="utf-8")
        (target / "SUMMARY.html").write_text(self._html(record, findings, tests, risks, skipped), encoding="utf-8")
        return target

    @staticmethod
    def _json(path: Path, data: Any) -> None:
        path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")

    def _timeline(self, path: Path, record: RunRecord) -> None:
        events = RuntimeEventStore(self.root).read(limit=50_000)
        with path.open("w", encoding="utf-8") as handle:
            for event in events:
                if event.timestamp < record.started_at_utc:
                    continue
                if record.finished_at_utc and event.timestamp > record.finished_at_utc:
                    continue
                handle.write(json.dumps(event.to_dict(), sort_keys=True, default=str) + "\n")

    @staticmethod
    def _markdown(record, findings, tests, risks, skipped, evidence, model_metrics) -> str:
        disclaimer = "\n> AUDIT_COMPLETE means the requested audit finished; it does not mean project acceptance PASS.\n" if record.status == "AUDIT_COMPLETE" else ""
        if record.status == "AUDIT_COMPLETE_LIMITED":
            disclaimer = "\n> [!WARNING]\n> AUDIT_COMPLETE_LIMITED: The audit completed but required AI analysis stages were unavailable. Findings are limited to the checks that actually ran.\n"
        
        techs = [f.get('message', '').replace('Technologies: ', '') for f in findings if 'Technologies:' in str(f.get('message', ''))]
        tech_str = techs[0] if techs else "Unknown"

        statically_inspected = ["Project structure", "File hashes", "Configuration files"]
        executed = ["None (verification blocked)"] if not tests else [t.get('name') for t in tests]
        
        lines = [
            f"# Engineering Office Run Report — {record.run_id}",
            "",
            f"**Status:** {record.status}",
            f"**Mode:** {record.mode}",
            f"**Objective:** {record.objective}",
            disclaimer,
            "## WHAT THIS PROJECT DOES",
            f"Based on static analysis, this project involves **{tech_str}**.",
        ]
        
        if skipped.get('qwen_analysis') or skipped.get('nemotron_review'):
            lines.extend([
                "Detailed architectural and behavioral analysis was not completed because one or more required AI analysis stages were unavailable.",
                "",
                "## Executive summary",
                "The project was indexed and scanned, but one or more AI reasoning stages were unavailable; see the skipped checks below.",
            ])
        else:
            executed_models = []
            for role, metrics in sorted(model_metrics.items()):
                if isinstance(metrics, dict):
                    provider = metrics.get("provider") or metrics.get("runtime")
                    model = metrics.get("model") or metrics.get("model_id")
                    if provider or model:
                        executed_models.append(f"{role}: {provider or 'model'} / {model or 'unknown'}")
            lines.extend([
                "Detailed architectural analysis was performed using the model executions recorded below." if executed_models else "No unavailable model stage was recorded, but no model provenance was captured.",
                "",
                "## Executive summary",
                ("AI-assisted analysis completed with recorded provenance: " + "; ".join(executed_models) + ".") if executed_models else "The audit completed without enough model provenance to name the models used.",
            ])

        lines.extend(["", "## AI Execution"])
        if model_metrics:
            for role, metrics in sorted(model_metrics.items()):
                if not isinstance(metrics, dict):
                    lines.append(f"- **{role}:** {metrics}")
                    continue
                provider = metrics.get("provider") or metrics.get("runtime") or "configured model"
                model = metrics.get("model") or metrics.get("model_id") or "unknown model"
                lines.append(f"- **{role}:** {provider} · {model}")
        else:
            lines.append("- No AI model execution was recorded for this run.")
        lines.append("- **Privacy:** Sanitized evidence only for any cloud escalation.")

        lines.extend([
            "",
            "## Architecture",
            "Not fully evaluated (requires deep reasoning).",
            "",
            "## Technologies",
            f"- {tech_str}",
            "",
            "## Important components",
            "Not evaluated.",
            "",
            "## How it runs",
            "Refer to the standard build/run instructions for this stack.",
            "",
            "## Tests",
        ])
        lines += [f"- [{row.get('status','UNKNOWN')}] {row.get('name','check')}" for row in tests] or ["- None run"]
        
        lines.extend([
            "",
            "## Findings",
        ])
        lines += [f"- [{row.get('severity','info')}] {row.get('message') or row}" for row in findings] or ["- None recorded"]

        lines.extend([
            "",
            "## Risks",
        ])
        lines += [f"- {row.get('risk') or row}" for row in risks] or ["- None recorded"]

        lines.extend([
            "",
            "## Skipped / unavailable checks",
        ])
        lines += [f"- {name}: {reason}" for name, reason in skipped.items()] or ["- None"]

        lines.extend([
            "",
            "## What was actually executed",
        ] + [f"- {e}" for e in executed] + [
            "",
            "## What was only statically inspected",
        ] + [f"- {s}" for s in statically_inspected] + [
            "",
            "## Not Verified",
            "- Runtime behavioral semantics",
            "- Deep architectural consistency",
            "",
            "## Recommendations",
            "- Resolve any skipped or unavailable checks above before treating the audit as comprehensive." if skipped else "- Follow the evidence-backed findings and independent verification results above.",
            "",
            "## Evidence",
        ])
        lines += [f"- {name}" for name in evidence] or ["- See timeline and project .office/evidence store"]
        
        return "\n".join(str(x) for x in lines) + "\n"

    @staticmethod
    def _html(record, findings, tests, risks, skipped) -> str:
        def text(value: Any) -> str:
            return escape(str(value))

        technologies = []
        for row in findings:
            message = str(row.get("message", "")) if isinstance(row, dict) else str(row)
            if message.startswith("Technologies:"):
                technologies = [part.strip() for part in message.split(":", 1)[1].split(",") if part.strip()]
                break

        def finding_cards() -> str:
            if not findings:
                return "<p class='empty'>No findings recorded.</p>"
            cards=[]
            for row in findings:
                if isinstance(row, dict):
                    severity=str(row.get("severity", "info")).lower()
                    message=row.get("message") or row
                else:
                    severity="info"; message=row
                cards.append(f"<div class='finding {text(severity)}'><span>{text(severity)}</span><p>{text(message)}</p></div>")
            return "".join(cards)

        test_rows = "".join(
            f"<tr><td>{text(row.get('name','check'))}</td><td><span class='status {text(str(row.get('status','UNKNOWN')).lower())}'>{text(row.get('status','UNKNOWN'))}</span></td></tr>"
            for row in tests
        ) or "<tr><td colspan='2'>No tests were recorded.</td></tr>"
        risk_rows = "".join(f"<li>{text(row.get('risk') if isinstance(row,dict) else row)}</li>" for row in risks) or "<li>None recorded</li>"
        skipped_rows = "".join(f"<li><strong>{text(name)}</strong>: {text(reason)}</li>" for name, reason in skipped.items()) or "<li>None</li>"
        tech_html = "".join(f"<span class='chip'>{text(item)}</span>" for item in technologies) or "<span class='chip muted'>Not detected</span>"
        limited = record.status == "AUDIT_COMPLETE_LIMITED"
        summary = (
            "This audit completed with limited AI analysis. Review the unavailable checks before treating the report as a deep engineering assessment."
            if limited else
            "This report summarizes the observable audit work. Audit completion is separate from independent project acceptance."
        )
        what = f"This project was detected as using {', '.join(technologies)}." if technologies else "The project was indexed and inspected, but its technology stack was not confidently identified."
        return f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{text(record.run_id)} · Engineering Office</title>
<style>
:root{{--paper:#f7f1df;--ink:#28332f;--muted:#68716c;--line:#c8c2ad;--ok:#39744b;--warn:#9a6921;--bad:#93443d}}
*{{box-sizing:border-box}}body{{margin:0;background:#ebe4d2;color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1040px;margin:32px auto;padding:0 20px 60px}}header,.card{{background:var(--paper);border:1px solid var(--line);box-shadow:0 3px 0 rgba(40,51,47,.12)}}header{{padding:26px}}h1{{margin:0 0 8px;font-size:28px}}h2{{margin:0 0 14px;font-size:19px}}.meta{{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}}.pill,.chip{{display:inline-block;padding:5px 9px;border:1px solid #9f9b88;background:#fffaf0;font-size:12px;font-weight:700}}.pill.limited{{background:#fff0cd;border-color:#c79848;color:#714e18}}.objective{{font-size:18px;margin:16px 0 0}}.grid{{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-top:16px}}.card{{padding:20px;margin-top:16px}}.grid .card{{margin-top:0}}.lead{{font-size:17px}}.muted{{color:var(--muted)}}.finding{{display:grid;grid-template-columns:90px 1fr;gap:12px;padding:10px 0;border-bottom:1px solid #ddd6c1}}.finding>span{{font-size:11px;font-weight:800;text-transform:uppercase}}.finding.warning>span{{color:var(--warn)}}.finding.blocker>span,.finding.error>span{{color:var(--bad)}}.finding p{{margin:0}}table{{width:100%;border-collapse:collapse}}td{{padding:9px;border-bottom:1px solid #ded7c4}}.status{{font-weight:800}}.status.pass{{color:var(--ok)}}.status.fail,.status.blocked{{color:var(--bad)}}ul{{padding-left:20px}}@media(max-width:760px){{.grid{{grid-template-columns:1fr}}main{{margin-top:14px}}}}
</style></head><body><main>
<header><div class='meta'><span class='pill {"limited" if limited else ""}'>{text(record.status)}</span><span class='pill'>{text(record.mode)}</span><span class='pill'>{text(record.run_id)}</span></div><h1>Engineering Office Run Report</h1><p class='objective'>{text(record.objective)}</p><p class='muted'>{text(summary)}</p></header>
<section class='card'><h2>WHAT THIS PROJECT DOES</h2><p class='lead'>{text(what)}</p><div>{tech_html}</div></section>
<div class='grid'><section class='card'><h2>Executive summary</h2><p>{text(summary)}</p></section><section class='card'><h2>Technologies</h2><div>{tech_html}</div></section></div>
<section class='card'><h2>Findings</h2>{finding_cards()}</section>
<div class='grid'><section class='card'><h2>Tests / checks</h2><table>{test_rows}</table></section><section class='card'><h2>Risks</h2><ul>{risk_rows}</ul></section></div>
<section class='card'><h2>Skipped / unavailable checks</h2><ul>{skipped_rows}</ul></section>
<section class='card'><h2>Verification note</h2><p>Audit completion does not by itself mean the project passed its independent acceptance gates. Use the recorded tests, evidence, timeline and verifier result for that decision.</p></section>
</main></body></html>"""

