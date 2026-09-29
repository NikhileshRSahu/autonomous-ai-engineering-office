from __future__ import annotations
import argparse
import json
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import webbrowser

from .agent_factory import AgentFactory
from .capabilities import CapabilityRegistry
from .config import OfficeConfig
from .discovery import ProjectDiscovery
from .models import Complexity, dataclass_to_jsonable
from .models_runtime import LocalModelManager, ModelRouter, OpenAICompatibleProvider, ScriptedProvider
from .office import OfficeEngine


def _json(data) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, default=str))



from .routing import build_model_router

def _router_from_config(path: str | None, project_root: str | Path | None = None) -> ModelRouter | None:
    return build_model_router(path, project_root=project_root)



def build_parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(prog="office", description="Autonomous AI Engineering Office")
    sub=p.add_subparsers(dest="command")
    sub.add_parser("help")
    for name in ["init","doctor","inspect","staff","plan","status","verify","memory","deliver"]:
        sp=sub.add_parser(name); sp.add_argument("path", nargs="?", default=".")
        if name in {"inspect","staff"}: sp.add_argument("--objective", default="understand and complete project")
    start=sub.add_parser("start"); start.add_argument("path"); start.add_argument("--objective", required=True); start.add_argument("--config"); start.add_argument("--plan-with-model", action="store_true")
    run=sub.add_parser("run"); run.add_argument("path", nargs="?", default="."); run.add_argument("--config"); run.add_argument("--max-iterations", type=int); run.add_argument("--parallelism", type=int); run.add_argument("--mode", choices=["fast-audit","check-report","fix","complete","custom"]); run.add_argument("--objective"); run.add_argument("--simulation", action="store_true", help="allow the audit planner to include expensive simulation when available"); run.add_argument("--auto", action="store_true", help="execute low-risk local work automatically; high-risk actions still require explicit approval")
    bench=sub.add_parser("benchmark"); bench.add_argument("benchmark_kind", nargs="?", default="suite"); bench.add_argument("benchmark_target", nargs="?"); bench.add_argument("path", nargs="?", default="."); bench.add_argument("--input"); bench.add_argument("--results", help="JSON file containing measured benchmark results")
    report=sub.add_parser("report", help="show the latest or selected permanent run report"); report.add_argument("path", nargs="?", default="."); report.add_argument("--run-id")
    index=sub.add_parser("index", help="inspect or rebuild the incremental project index"); index_sub=index.add_subparsers(dest="index_action", required=True)
    for action in ["status","rebuild"]:
        isp=index_sub.add_parser(action); isp.add_argument("path", nargs="?", default=".")
    demo=sub.add_parser("demo"); demo.add_argument("--workspace", required=False); demo.add_argument("--force", action="store_true")
    for name in ["pause", "stop", "resume", "approvals"]:
        sp=sub.add_parser(name); sp.add_argument("path", nargs="?", default=".")
        if name == "resume": sp.add_argument("--reset-blocked", action="store_true")
    for name in ["approve", "deny"]:
        sp=sub.add_parser(name); sp.add_argument("path", nargs="?", default="."); sp.add_argument("approval_id")
    obj=sub.add_parser("objective"); obj.add_argument("path", nargs="?", default="."); obj.add_argument("--set", required=True, dest="objective")
    repl=sub.add_parser("replace-agent"); repl.add_argument("path", nargs="?", default="."); repl.add_argument("--old", required=True); repl.add_argument("--expertise", required=True)
    plan_model=sub.add_parser("plan-model"); plan_model.add_argument("path", nargs="?", default="."); plan_model.add_argument("--config", required=True); plan_model.add_argument("--tier", choices=[c.value for c in Complexity], default=Complexity.HIGH.value)
    intake=sub.add_parser("intake"); intake.add_argument("source"); intake.add_argument("destination"); intake.add_argument("--zip", action="store_true", dest="is_zip")
    ui=sub.add_parser("ui", help="open the local user-friendly Engineering Office control room"); ui.add_argument("path", nargs="?", default="."); ui.add_argument("--host", default="127.0.0.1"); ui.add_argument("--port", type=int, default=8765); ui.add_argument("--no-open", action="store_true"); ui.add_argument("--app", action="store_true", help="prefer Chromium/Edge app-window mode when available")
    model=sub.add_parser("model", help="inspect and control Office-owned local model servers")
    model_sub=model.add_subparsers(dest="model_action", required=True)
    ms=model_sub.add_parser("status"); ms.add_argument("path", nargs="?", default="."); ms.add_argument("--config", required=True)
    for action in ["start","switch","stop"]:
        sp=model_sub.add_parser(action); sp.add_argument("name"); sp.add_argument("path", nargs="?", default="."); sp.add_argument("--config", required=True)
    msa=model_sub.add_parser("stop-all"); msa.add_argument("path", nargs="?", default="."); msa.add_argument("--config", required=True)
    mc=model_sub.add_parser("cold-start"); mc.add_argument("path", nargs="?", default="."); mc.add_argument("--config", required=True); mc.add_argument("--sequence", required=True, help="comma-separated local model names, e.g. qwen,nemotron,qwen"); mc.add_argument("--output")
    return p


def main(argv: list[str] | None = None) -> int:
    parser=build_parser()
    if argv is not None and len(argv) == 1 and argv[0] in {"-h", "--help"}:
        parser.print_help()
        return 0
    args=parser.parse_args(argv)
    if args.command in {None,"help"}:
        parser.print_help(); return 0
    try:
        if args.command == "init": return _cmd_init(Path(args.path))
        if args.command == "doctor": return _cmd_doctor(Path(args.path))
        if args.command == "inspect":
            _json(dataclass_to_jsonable(ProjectDiscovery().inspect(args.path,args.objective))); return 0
        if args.command == "staff":
            project=ProjectDiscovery().inspect(args.path,args.objective)
            _json([dataclass_to_jsonable(a) for a in AgentFactory(CapabilityRegistry.default()).staff(project)]); return 0
        if args.command == "start":
            cfg = OfficeConfig.load(args.config) if args.config else OfficeConfig()
            router = _router_from_config(args.config, args.path)
            engine = OfficeEngine(args.path, model_router=router, max_task_iterations=cfg.max_task_iterations, parallelism=cfg.parallelism, max_feedback_cycles=cfg.max_feedback_cycles)
            summary = engine.start(args.objective)
            if args.plan_with_model:
                if router is None:
                    raise RuntimeError("--plan-with-model requires --config with a routed model provider")
                planned = engine.plan_with_model(router.route(Complexity.HIGH))
                summary["tasks"] = planned["tasks"]
                summary["planning_source"] = "model"
            _json(summary); return 0
        if args.command == "plan":
            engine=OfficeEngine(args.path); _json(json.loads((engine.office_dir/"plan.json").read_text())); return 0
        if args.command == "run":
            cfg = OfficeConfig.load(args.config) if args.config else OfficeConfig()
            engine=OfficeEngine(
                args.path,
                model_router=_router_from_config(args.config, args.path),
                max_task_iterations=args.max_iterations if args.max_iterations is not None else cfg.max_task_iterations,
                parallelism=args.parallelism if args.parallelism is not None else cfg.parallelism,
                max_feedback_cycles=cfg.max_feedback_cycles,
            )
            if args.objective and (Path(args.path).resolve()/".office"/"project.json").is_file():
                engine.update_objective(args.objective)
            mode=args.mode or cfg.default_run_mode
            _json(engine.run_mode(mode,args.objective,max_context_files=cfg.fast_audit_max_context_files,max_context_chars=cfg.fast_audit_max_context_chars,simulation_requested=bool(args.simulation))); return 0
        if args.command == "status": _json(OfficeEngine(args.path).status()); return 0
        if args.command == "verify": _json(OfficeEngine(args.path).verify()); return 0
        if args.command == "memory":
            engine=OfficeEngine(args.path); project=engine._load_project(); _json(engine.store.list_memory(project.project_id)); return 0
        if args.command == "deliver": print(OfficeEngine(args.path).deliver()); return 0
        if args.command == "report":
            from .run_records import RunRecordStore
            store=RunRecordStore(args.path); record=store.load(args.run_id) if args.run_id else store.latest()
            if record is None:
                _json({"available":False,"message":"No run report exists yet."}); return 1
            directory=Path(args.path).resolve()/".office"/"reports"/record.run_id
            report=directory/"REPORT.md"
            _json({"available":report.is_file(),"run_id":record.run_id,"status":record.status,"directory":str(directory),"report":str(report) if report.is_file() else None}); return 0 if report.is_file() else 1
        if args.command == "index":
            from .project_index import ProjectIndex
            root=Path(args.path).resolve()
            if args.index_action == "rebuild":
                office=root/".office"/"index"
                for name in ["index.db","manifest.json","generation.json"]:
                    (office/name).unlink(missing_ok=True)
                idx=ProjectIndex(root); update=idx.update(); _json(idx.status()|{"rebuilt":True,"changed":update.changed,"removed":update.removed}); return 0
            _json(ProjectIndex(root).status()); return 0
        if args.command == "benchmark":
            kind = args.benchmark_kind
            # Backward compatibility: `office benchmark PATH --input cases.json`.
            if kind not in {"suite", "residency", "speculative", "nemotron-runtime"}:
                args.path, kind = kind, "suite"
            if kind == "suite":
                from .benchmark import BenchmarkSuite
                suite=BenchmarkSuite.from_json(args.input) if args.input else BenchmarkSuite([])
                _json(suite.summary()); return 0
            project_path = args.path
            target = args.benchmark_target
            if kind in {"residency", "nemotron-runtime"} and target and args.path == ".":
                project_path, target = target, None
            from .runtime_benchmarks import RuntimeBenchmarkRegistry
            registry = RuntimeBenchmarkRegistry(project_path)
            if not args.results:
                _json({"benchmark":kind,"target":target,"status":"NEEDS_MEASUREMENTS","message":"Run the benchmark adapter on the target laptop and provide --results JSON; no optimization is enabled without measurements.","registry":str(registry.path)}); return 0
            raw=json.loads(Path(args.results).read_text())
            fingerprint=str(raw.get("fingerprint") or registry.fingerprint(raw.get("hardware",{}),raw.get("runtime",{}),raw.get("model",{}),raw.get("config",{})))
            if kind == "speculative":
                from .runtime_benchmarks import QwenSpeculativeBenchmark
                decision=QwenSpeculativeBenchmark(registry).evaluate(fingerprint,baseline=raw["baseline"],candidates=raw.get("candidates",{}))
            elif kind == "nemotron-runtime":
                from .runtime_benchmarks import NemotronRuntimeBenchmark
                decision=NemotronRuntimeBenchmark(registry).evaluate(fingerprint,llama=raw["llama"],challenger_capability=raw.get("challenger_capability",{}),challenger=raw.get("challenger"))
            else:
                registry.record("residency", {"fingerprint":fingerprint, **raw.get("decision",{})})
                decision=registry.selected("residency",fingerprint) or {"fingerprint":fingerprint,"selected":False}
            _json(decision.to_dict() if hasattr(decision,"to_dict") else decision); return 0
        if args.command == "demo": return _cmd_demo(args.workspace,args.force)
        if args.command in {"pause", "stop", "resume"}:
            engine=OfficeEngine(args.path)
            if args.command == "pause": engine.pause()
            elif args.command == "stop": engine.stop()
            else: engine.resume(reset_blocked=args.reset_blocked)
            _json(engine.control.state()); return 0
        if args.command == "approvals":
            engine=OfficeEngine(args.path); _json([dataclass_to_jsonable(x) for x in engine.approvals.list()]); return 0
        if args.command in {"approve", "deny"}:
            engine=OfficeEngine(args.path)
            item=engine.approvals.approve(args.approval_id) if args.command == "approve" else engine.approvals.deny(args.approval_id)
            _json(dataclass_to_jsonable(item)); return 0
        if args.command == "objective":
            _json(dataclass_to_jsonable(OfficeEngine(args.path).update_objective(args.objective))); return 0
        if args.command == "replace-agent":
            _json(dataclass_to_jsonable(OfficeEngine(args.path).replace_agent(args.old,args.expertise))); return 0
        if args.command == "plan-model":
            router=_router_from_config(args.config, args.path)
            if router is None: raise RuntimeError("model config produced no router")
            provider=router.route(Complexity(args.tier))
            _json(OfficeEngine(args.path).plan_with_model(provider)); return 0
        if args.command == "model":
            router=_router_from_config(args.config, args.path)
            if router is None or router.lifecycle_manager is None:
                raise RuntimeError("model command requires local_models in --config")
            manager=router.lifecycle_manager
            if args.model_action == "status":
                _json({"current_model":manager.current_model,"models":[manager.status(name) for name in manager.specs]}); return 0
            if args.model_action in {"start","switch"}:
                _json(manager.ensure(args.name)); return 0
            if args.model_action == "stop":
                _json(manager.stop(args.name)); return 0
            if args.model_action == "stop-all":
                _json({"stopped":manager.stop_all_owned()}); return 0
            if args.model_action == "cold-start":
                sequence=[part.strip() for part in args.sequence.split(",") if part.strip()]
                output=args.output or str(Path(args.path).resolve()/".office"/"benchmarks"/"model-cold-start.json")
                _json(manager.cold_start_validate(sequence,output)); return 0
        if args.command == "ui": return _cmd_ui(Path(args.path), args.host, args.port, args.no_open, args.app)
        if args.command == "intake":
            from .intake import ProjectIntake
            intake=ProjectIntake()
            result=intake.from_zip(args.source,args.destination) if args.is_zip else intake.from_directory(args.source)
            _json({"root":str(result.root),"source":str(result.source),"extracted_files":result.extracted_files}); return 0
    except Exception as exc:
        print(json.dumps({"error":type(exc).__name__,"message":str(exc)}, indent=2), file=sys.stderr)
        return 2
    return 2


def _cmd_init(path: Path) -> int:
    path=path.resolve(); path.mkdir(parents=True,exist_ok=True)
    office=path/".office"; office.mkdir(exist_ok=True)
    config=office/"config.json"
    if not config.exists():
        config.write_text(json.dumps({"model_profiles":{},"routing":{},"max_feedback_cycles":4,"max_task_iterations":6,"parallelism":2,"default_run_mode":"complete","fast_audit_max_context_files":30,"fast_audit_max_context_chars":200000},indent=2))
    _json({"office":str(office),"config":str(config),"next":"office start PATH --objective '...'"}); return 0


def _cmd_doctor(path: Path) -> int:
    def has(cmd): return shutil.which(cmd) is not None
    data={
        "project_root":str(path.resolve()),
        "python":{"ok":sys.version_info >= (3,11),"version":sys.version.split()[0]},
        "git":{"ok":has("git"),"path":shutil.which("git")},
        "pytest":{"ok":has("pytest"),"path":shutil.which("pytest")},
        "office_state":{"exists":(path.resolve()/".office").exists()},
    }
    _json(data); return 0 if data["python"]["ok"] and data["git"]["ok"] else 1


def _demo_response() -> str:
    return json.dumps({
        "status":"COMPLETE",
        "observations":["acceptance test shows calculator.add(2, 3) returns -1 instead of 5"],
        "interpretations":["the add implementation subtracts instead of adding"],
        "hypotheses":[{
            "hypothesis_id":"H1","claim":"calculator.add uses the wrong arithmetic operator",
            "observations":["test_add fails"],"evidence_for":["source returns a - b"],"evidence_against":[],
            "alternatives":["test expectation wrong"],"confidence":0.99,"discriminating_test":"run acceptance test after changing only operator",
            "expected_if_true":"test_add passes","expected_if_false":"test_add remains failing"
        }],
        "actions":[{"tool":"filesystem.write","args":{"path":"src/calculator.py","content":"def add(a, b):\n    return a + b\n"},"reason":"minimal correction supported by failing test"}],
        "tests":["python -m unittest discover -s tests -q"],"risks":[],"specialist_requests":[],"research_requests":[],"handoff":"independent verification"
    })


def _cmd_demo(workspace: str | None, force: bool) -> int:
    root=Path(workspace).resolve() if workspace else Path(tempfile.mkdtemp(prefix="engineering-office-demo-"))
    if root.exists() and any(root.iterdir()):
        if not force: raise RuntimeError("demo workspace is not empty; use --force for a dedicated disposable workspace")
        shutil.rmtree(root)
    root.mkdir(parents=True,exist_ok=True); (root/"src").mkdir(); (root/"tests").mkdir()
    (root/"src"/"__init__.py").write_text("")
    (root/"src"/"calculator.py").write_text("def add(a, b):\n    return a - b\n")
    (root/"tests"/"test_calculator.py").write_text("import unittest\nfrom src.calculator import add\n\nclass CalculatorTest(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\nif __name__ == '__main__':\n    unittest.main()\n")
    (root/"pyproject.toml").write_text('[project]\nname="office-demo"\nversion="0.0.0"\n')
    (root/"acceptance.json").write_text(json.dumps({"gates":[{"name":"unittest","command":"python -m unittest discover -s tests -q","expected_exit":0}],"required_evidence":[]}))
    provider=ScriptedProvider([_demo_response()]); router=ModelRouter({c:provider for c in Complexity})
    engine=OfficeEngine(root,model_router=router,max_task_iterations=2)
    start=engine.start("Repair the seeded calculator defect and verify it without weakening tests.")
    run=engine.run()
    delivery=engine.deliver() if run["project_state"]=="PASS" else None
    _json({"workspace":str(root),"start":start,"run":run,"delivery":delivery})
    return 0 if run["project_state"]=="PASS" else 1


def _validate_ui_host(host: str) -> str:
    value = host.strip()
    if value.lower() == "localhost":
        return value
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise ValueError("UI host must be a loopback address (127.0.0.1, ::1, or localhost)") from exc
    if not address.is_loopback:
        raise ValueError("UI host must be a loopback address; remote Control Room exposure is disabled")
    return value


def _cmd_ui(path: Path, host: str, port: int, no_open: bool, app_mode: bool) -> int:
    from .ui_server import OfficeUIServer
    host = _validate_ui_host(host)
    server = OfficeUIServer(path, host=host, port=port)
    display_host = f"[{host}]" if ":" in host else host
    url = f"http://{display_host}:{server.port}/"
    print(json.dumps({"ui": url, "project_root": str(path.resolve()), "mode": "app" if app_mode else "browser"}, indent=2))
    if not no_open:
        opened = False
        if app_mode:
            for cmd in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge"]:
                exe = shutil.which(cmd)
                if exe:
                    subprocess.Popen([exe, f"--app={url}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    opened = True
                    break
        if not opened:
            webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
