from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any
import json

from .eta import EtaEstimator
from .fast_audit import FastAuditPlanner
from .models import Complexity, dataclass_to_jsonable, ProjectState
from .project_index import ProjectIndex
from .reporting import RunReportBuilder
from .run_records import RunCoordinator


_TEXT_SUFFIXES = {
    '.py','.pyi','.js','.ts','.tsx','.jsx','.json','.yaml','.yml','.xml','.urdf','.xacro',
    '.sdf','.launch','.md','.txt','.toml','.ini','.cfg','.cmake','.sh','.bash','.cpp','.cc',
    '.c','.h','.hpp','.java','.rs','.go','.html','.css','.sql',
}


class FastAuditRunner:
    """Read-only project audit orchestrator.

    The runner deliberately does not reuse the implementation task loop: audit modes
    must never need a candidate write in order to produce a useful report.  It uses
    the same model router/lifecycle manager, runtime event store and independent
    verifier, but sends only a bounded changed-file dossier to the Qwen analysis
    phase and one compact dossier to the strong reviewer.
    """

    def __init__(self, engine, *, max_context_files: int = 30, max_context_chars: int = 200_000):
        self.engine = engine
        self.root = Path(engine.root).resolve()
        self.max_context_files = max(1, int(max_context_files))
        self.max_context_chars = max(10_000, int(max_context_chars))

    def run(self, mode: str, objective: str | None = None, *, simulation_requested: bool = False) -> dict[str, Any]:
        mode = str(mode).lower().strip()
        if mode not in {'fast-audit', 'check-report'}:
            raise ValueError('FastAuditRunner supports fast-audit or check-report')
        project = self.engine._load_project()
        objective = (objective or project.objective or 'Check this project and give a report.').strip()
        index = ProjectIndex(self.root)
        coordinator = RunCoordinator(self.root, project_id=project.project_id, event_store=self.engine.runtime_events)
        self.engine.run_coordinator = coordinator
        # First compute the change set, then lock the stage contract for this run.
        record = coordinator.start(mode, objective, ['IMPORT','INDEX','ANALYZE','TEST','REVIEW','REPORT'])
        findings: list[dict[str, Any]] = []
        risks: list[dict[str, Any]] = []
        tests: list[dict[str, Any]] = []
        model_metrics: dict[str, Any] = {}
        skipped: dict[str, str] = {}
        update = None
        verification: dict[str, Any] = {'verdict':'BLOCKED','checks':[],'reasons':['verification did not run']}
        try:
            coordinator.transition('IMPORT', 'PASS', 'Existing project floor ready')
            coordinator.transition('INDEX', 'RUNNING', 'Hashing project content')
            update = index.update()
            plan = FastAuditPlanner().plan(update, simulation_requested=simulation_requested)
            coordinator.transition('INDEX', 'PASS', f'{len(update.changed)} changed · {len(update.unchanged)} reused · {len(update.removed)} removed')

            coordinator.transition('ANALYZE', 'RUNNING', 'Inspecting project and changed content')
            findings.extend(self._deterministic_findings(project, update))
            risks.extend({'risk': item, 'source': 'project-discovery'} for item in project.risk_areas)
            skipped.update(plan.skipped)
            qwen = self._qwen_analysis(project, update, objective)
            findings.extend(qwen.get('findings', [])); risks.extend(qwen.get('risks', []))
            model_metrics.update(qwen.get('metrics', {}))
            if qwen.get('skipped'):
                skipped['qwen_analysis'] = qwen['skipped']
            coordinator.transition('ANALYZE', 'PASS', f'{len(findings)} findings collected')

            coordinator.transition('TEST', 'RUNNING', 'Running configured independent checks')
            verification = self.engine.verify()
            for check in verification.get('checks', []):
                tests.append({
                    'name': check.get('name', 'acceptance'),
                    'status': 'PASS' if check.get('passed') else 'FAIL',
                    'returncode': check.get('returncode'),
                    'stdout': check.get('stdout',''),
                    'stderr': check.get('stderr',''),
                })
            for reason in verification.get('reasons', []):
                findings.append({'severity':'blocker' if verification.get('verdict') == 'BLOCKED' else 'warning', 'message': reason, 'source':'verification'})
            coordinator.transition('TEST', 'PASS' if verification.get('verdict') == 'PASS' else 'WARN', f"Acceptance result: {verification.get('verdict','UNKNOWN')}")

            coordinator.transition('REVIEW', 'RUNNING', 'Consolidating one strong review')
            review = self._nemotron_review(project, objective, findings, tests, risks)
            findings.extend(review.get('findings', [])); risks.extend(review.get('risks', []))
            model_metrics.update(review.get('metrics', {}))
            if review.get('skipped'):
                skipped['nemotron_review'] = review['skipped']
            coordinator.transition('REVIEW', 'PASS', 'Review dossier completed')

            coordinator.transition('REPORT', 'RUNNING', 'Writing permanent audit report')
            final_status = 'AUDIT_COMPLETE'
            qwen_err = skipped.get('qwen_analysis', '')
            nemo_err = skipped.get('nemotron_review', '')
            if (qwen_err and "No changed files" not in qwen_err) or (nemo_err and "No changed files" not in nemo_err):
                final_status = 'AUDIT_COMPLETE_LIMITED'
            
            record = coordinator.finish(final_status, {
                'verification_verdict': verification.get('verdict'),
                'findings': len(findings), 'tests': len(tests), 'risks': len(risks),
            })
            self.engine.store.set_project_state(project.project_id, getattr(ProjectState, final_status))
            report_dir = RunReportBuilder(self.root).build(
                record, findings=findings, tests=tests, risks=risks, model_metrics=model_metrics,
                skipped=skipped, index_status=index.status(),
            )
            self._record_timing(record, project.project_type)
            return {
                'run_id': record.run_id, 'mode': mode, 'status': record.status,
                'report_dir': str(report_dir), 'verification': verification,
                'index': index.status(), 'findings': findings, 'risks': risks,
                'skipped': skipped, 'model_metrics': model_metrics,
            }
        except Exception as exc:
            # Audit failure is still reportable.  Do not mutate the source project to
            # recover from an audit problem.
            try:
                active = coordinator.active()
                if active.current_stage:
                    coordinator.transition(active.current_stage, 'BLOCKED', str(exc))
                record = coordinator.finish('BLOCKED', {'error': str(exc)})
                report_dir = RunReportBuilder(self.root).build(
                    record, findings=findings + [{'severity':'blocker','message':str(exc),'source':'audit'}],
                    tests=tests, risks=risks, model_metrics=model_metrics, skipped=skipped,
                    index_status=index.status(),
                )
                self._record_timing(record, project.project_type)
                return {'run_id':record.run_id,'mode':mode,'status':'BLOCKED','report_dir':str(report_dir),'verification':verification,'error':str(exc),'findings':findings,'risks':risks,'skipped':skipped}
            finally:
                pass

    def _deterministic_findings(self, project, update) -> list[dict[str, Any]]:
        rows = [
            {'severity':'info','message':f'Project type: {project.project_type}','source':'discovery'},
            {'severity':'info','message':f'Technologies: {", ".join(project.technologies) or "not detected"}','source':'discovery'},
            {'severity':'info','message':f'Index: {len(update.changed)} changed, {len(update.unchanged)} unchanged, {len(update.removed)} removed','source':'index'},
        ]
        rows += [{'severity':'warning','message':item,'source':'discovery'} for item in project.broken_components]
        rows += [{'severity':'warning','message':item,'source':'discovery'} for item in project.unknowns]
        return rows

    def _changed_dossier(self, update) -> list[dict[str, str]]:
        candidates = list(update.changed)
        # Prefer architecture/config/test files before large generated or asset files.
        def score(rel: str):
            name = Path(rel).name.lower(); suffix = Path(rel).suffix.lower()
            priority = 0
            if name.startswith('readme') or name in {'pyproject.toml','package.json','cmakelists.txt','acceptance.json'}: priority -= 20
            if 'test' in rel.lower(): priority -= 10
            if suffix in {'.yaml','.yml','.launch','.xacro','.urdf','.sdf'}: priority -= 8
            return (priority, len(Path(rel).parts), rel)
        rows=[]; used=0
        for rel in sorted(candidates, key=score):
            if len(rows) >= self.max_context_files or used >= self.max_context_chars:
                break
            path = (self.root / rel).resolve()
            if path.suffix.lower() not in _TEXT_SUFFIXES or not path.is_file() or self.root not in path.parents:
                continue
            try:
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            remaining = self.max_context_chars - used
            text = text[:remaining]
            rows.append({'path':rel,'content':text})
            used += len(text)
        return rows

    @staticmethod
    def _response_metrics(response, provider=None) -> dict[str, Any]:
        metrics: dict[str, Any] = dict(response.usage or {})
        raw = response.raw if isinstance(response.raw, dict) else {}
        provider_name = raw.get("provider")
        model_name = raw.get("model")
        if provider_name is None and provider is not None:
            provider_name = getattr(provider, "last_provider", None) or provider.__class__.__name__
        if model_name is None and provider is not None:
            active = provider
            if getattr(provider, "last_provider", None) == "local":
                active = getattr(provider, "local_provider", None) or provider
            profile = getattr(active, "profile", None)
            if profile is not None:
                model_name = getattr(profile, "model", None)
        if provider_name is not None:
            metrics["provider"] = str(provider_name)
        if model_name is not None:
            metrics["model"] = str(model_name)
        metrics["calls"] = 1
        return metrics


    @staticmethod
    def _parse_model_json(content: str) -> dict[str, Any]:
        try:
            raw = json.loads(content)
        except Exception:
            return {'findings':[{'severity':'warning','message':'Local model returned non-JSON audit output; preserved as reviewer note.','detail':content[:2000]}], 'risks':[]}
        return raw if isinstance(raw, dict) else {'findings':[], 'risks':[]}

    def _qwen_analysis(self, project, update, objective: str) -> dict[str, Any]:
        if self.engine.model_router is None:
            return {'findings':[], 'risks':[], 'metrics':{}, 'skipped':'No routed analysis model is configured; deterministic audit continued.'}
        dossier = self._changed_dossier(update)
        if not dossier:
            return {'findings':[{'severity':'info','message':'No changed project files required fresh model analysis.','source':'incremental-index'}], 'risks':[], 'metrics':{}, 'skipped':'No changed files; prior project/index knowledge reused.'}
        try:
            provider = self.engine.model_router.route(Complexity.LOW)
            self.engine._emit_runtime('review.started','Qwen engineering audit batch started',project_id=project.project_id,agent_id='Audit Engineer',payload={'family':'qwen','files':len(dossier)},source='audit')
            messages=[
                {'role':'system','content':'You are a read-only engineering auditor. Return JSON only with keys findings (list of {severity,message,source}), risks (list of {risk,source}), recommended_checks (list). Do not propose source edits as actions.'},
                {'role':'user','content':json.dumps({'objective':objective,'project':dataclass_to_jsonable(project),'changed_files':dossier},default=str)},
            ]
            response=provider.complete(messages,response_format={'type':'json_object'})
            raw=self._parse_model_json(response.content)
            self.engine._emit_runtime('review.finished','Qwen engineering audit batch finished',project_id=project.project_id,agent_id='Audit Engineer',payload={'family':'qwen'},source='audit')
            return {'findings':list(raw.get('findings',[])), 'risks':list(raw.get('risks',[])), 'metrics':{'analysis':self._response_metrics(response, provider)}}
        except Exception as exc:
            return {'findings':[{'severity':'warning','message':f'Qwen audit unavailable: {exc}','source':'model'}], 'risks':[], 'metrics':{}, 'skipped':str(exc)}

    def _nemotron_review(self, project, objective: str, findings, tests, risks) -> dict[str, Any]:
        if self.engine.model_router is None:
            return {'findings':[], 'risks':[], 'metrics':{}, 'skipped':'No strong review model is configured; deterministic results were preserved.'}
        try:
            provider = self.engine.model_router.route(Complexity.HIGH)
            self.engine._emit_runtime('review.started','Strong adversarial audit review started',project_id=project.project_id,agent_id='Adversarial Reviewer',payload={'family':'nemotron'},source='audit')
            messages=[
                {'role':'system','content':'You are the strong adversarial reviewer for a read-only engineering audit. Return JSON only with keys findings (list of {severity,message,source}), risks (list of {risk,source}), review (string). Challenge unsupported conclusions; never declare project acceptance PASS.'},
                {'role':'user','content':json.dumps({'objective':objective,'project_type':project.project_type,'findings':findings,'tests':tests,'risks':risks},default=str)},
            ]
            response=provider.complete(messages,response_format={'type':'json_object'})
            raw=self._parse_model_json(response.content)
            self.engine._emit_runtime('review.finished','Strong adversarial audit review finished',project_id=project.project_id,agent_id='Adversarial Reviewer',payload={'family':'nemotron'},source='audit')
            return {'findings':list(raw.get('findings',[])), 'risks':list(raw.get('risks',[])), 'metrics':{'review':self._response_metrics(response, provider)}}
        except Exception as exc:
            return {'findings':[{'severity':'warning','message':f'Strong review unavailable: {exc}','source':'model'}], 'risks':[], 'metrics':{}, 'skipped':str(exc)}

    def _record_timing(self, record, project_type: str) -> None:
        manager = getattr(getattr(self.engine, 'model_router', None), 'lifecycle_manager', None)
        model_state = 'warm' if manager is not None and getattr(manager, 'current_model', None) else 'cold'
        EtaEstimator(self.root).record(record, {
            'project_type': project_type,
            'model_state': model_state,
            'simulation_level': 'none',
            'runtime_strategy': record.model_strategy or 'default',
        })
