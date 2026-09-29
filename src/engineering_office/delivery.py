from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import subprocess

from .models import ProjectState
from .storage import OfficeStore


class DeliveryError(RuntimeError):
    pass


class DeliveryManager:
    def __init__(self, project_root: str | Path, store: OfficeStore):
        self.root = Path(project_root).resolve()
        self.store = store
        self.office = self.root / ".office"

    def create(self, project_id: str, status: dict[str, Any]) -> Path:
        if self.store.get_project_state(project_id) is not ProjectState.PASS:
            raise DeliveryError("project must be independently verified PASS before delivery")
        tasks = self.store.list_tasks(project_id)
        if any(state.value != "PASS" for _, state in tasks):
            raise DeliveryError("all project tasks must be PASS before delivery")
        critical_risks = list(status.get("critical_risks", []))
        if critical_risks:
            raise DeliveryError("unresolved critical risks prevent delivery: " + "; ".join(map(str, critical_risks)))
        out = self.office / "delivery"
        out.mkdir(parents=True, exist_ok=True)
        (out / "acceptance-report.json").write_text(json.dumps(status.get("verification", {}), indent=2, sort_keys=True, default=str))
        (out / "test-report.json").write_text(json.dumps(status.get("task_results", []), indent=2, sort_keys=True, default=str))
        (out / "evidence-summary.json").write_text(json.dumps(status.get("evidence", []), indent=2, sort_keys=True, default=str))
        (out / "unresolved-risks.md").write_text("# Unresolved Risks\n\nNo unresolved critical risks were recorded at verified delivery. Non-critical project-specific risks remain visible in project evidence and should be reviewed before production use.\n")
        (out / "architecture.md").write_text(self._architecture_summary(project_id))
        (out / "reproducibility.md").write_text(
            "# Reproducibility\n\nRun the acceptance gates stored in `.office/acceptance/project.json` from the project root.\n"
            "Review `.office/evidence/` and `.office/state.db` for the audit trail.\n"
        )
        diff = self._git_diff_summary()
        (out / "changes.md").write_text("# Change Summary\n\n```text\n" + diff + "\n```\n")
        (out / "project-pointer.json").write_text(json.dumps({
            "project_root": str(self.root),
            "copy_policy": "delivery references the verified project workspace; copy/archive the project separately when portability is required",
        }, indent=2, sort_keys=True))
        manifest = {
            "project_id": project_id,
            "project_root": str(self.root),
            "state": "PASS",
            "delivery_files": sorted(p.name for p in out.iterdir() if p.is_file()),
        }
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
        return out

    def _architecture_summary(self, project_id: str) -> str:
        project = self.store.get_project(project_id)
        plan_path = self.office / "plan.json"
        task_lines=[]
        if plan_path.exists():
            try:
                plan=json.loads(plan_path.read_text())
                task_lines=[f"- `{t.get('task_id','?')}` — {t.get('owner','?')}: {t.get('goal','')}" for t in plan.get('tasks',[])]
            except (OSError, json.JSONDecodeError):
                task_lines=[]
        return (
            "# Architecture Summary\n\n"
            f"**Project type:** {project.project_type}\n\n"
            f"**Objective:** {project.objective}\n\n"
            f"**Technologies:** {', '.join(project.technologies) or 'Not detected'}\n\n"
            f"**Required domains:** {', '.join(project.required_domains) or 'Not detected'}\n\n"
            "## Executed Task Plan\n\n" + ("\n".join(task_lines) if task_lines else "No serialized task plan was available.") + "\n"
        )

    def _git_diff_summary(self) -> str:
        try:
            proc = subprocess.run(["git", "diff", "--stat"], cwd=self.root, text=True, capture_output=True, timeout=20)
            return proc.stdout.strip() or "No git diff summary available (clean tree or non-git project)."
        except (OSError, subprocess.SubprocessError):
            return "No git diff summary available."
