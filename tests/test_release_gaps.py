from pathlib import Path
import io
import json
import zipfile

import pytest

from engineering_office.intake import ProjectIntake, IntakeError
from engineering_office.security import PermissionSet, SecurityError
from engineering_office.tools import FileWriteTool, ReplaceTextTool
from engineering_office.integrations import CommandToolAdapter, ExtensionRegistry
from engineering_office.cli import main


def make_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for name, content in entries.items():
            z.writestr(name, content)


def test_zip_intake_extracts_project_safely(tmp_path: Path):
    archive = tmp_path / "project.zip"
    make_zip(archive, {"repo/README.md": "hello", "repo/src/app.py": "print('ok')\n"})
    dest = tmp_path / "workspace"
    result = ProjectIntake().from_zip(archive, dest)
    assert result.root == dest / "repo"
    assert (result.root / "src/app.py").read_text() == "print('ok')\n"


def test_zip_intake_rejects_zip_slip(tmp_path: Path):
    archive = tmp_path / "evil.zip"
    make_zip(archive, {"../escape.txt": "owned"})
    with pytest.raises(IntakeError, match="unsafe zip member"):
        ProjectIntake().from_zip(archive, tmp_path / "workspace")
    assert not (tmp_path / "escape.txt").exists()


def test_candidate_write_tool_cannot_modify_office_or_git_internal_state(tmp_path: Path):
    (tmp_path / ".office").mkdir(); (tmp_path / ".git").mkdir()
    perms = PermissionSet(read_scopes=["."], write_scopes=["."])
    writer = FileWriteTool(tmp_path, perms)
    replacer = ReplaceTextTool(tmp_path, perms)
    with pytest.raises(SecurityError, match="protected"):
        writer.execute({"path": ".office/acceptance/project.json", "content": "{}"})
    with pytest.raises(SecurityError, match="protected"):
        writer.execute({"path": ".git/config", "content": "bad"})
    with pytest.raises(SecurityError, match="protected"):
        replacer.execute({"path": ".office/state.db", "old": "x", "new": "y", "create_if_missing": True})


def test_command_adapter_and_extension_registry_are_shell_free(tmp_path: Path):
    adapter = CommandToolAdapter(
        name="echo-json",
        command=["python", "-c", "import json,sys; d=json.load(sys.stdin); print(json.dumps({'seen':d['value']}))"],
        timeout=10,
    )
    registry = ExtensionRegistry(); registry.register(adapter)
    result = registry.execute("echo-json", {"value": 7}, tmp_path)
    assert result.ok is True
    assert json.loads(result.stdout)["seen"] == 7
    assert registry.names() == ["echo-json"]


def test_cli_governance_commands_persist_control_and_approvals(tmp_path: Path, capsys):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    assert main(["start", str(tmp_path), "--objective", "finish project"]) == 0
    capsys.readouterr()

    assert main(["pause", str(tmp_path)]) == 0
    paused = json.loads(capsys.readouterr().out)
    assert paused["paused"] is True

    assert main(["resume", str(tmp_path)]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["paused"] is False

    assert main(["objective", str(tmp_path), "--set", "new objective"]) == 0
    changed = json.loads(capsys.readouterr().out)
    assert changed["objective"] == "new objective"

    assert main(["approvals", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_discovery_and_staffing_cover_non_software_engineering_domains(tmp_path: Path):
    from engineering_office.discovery import ProjectDiscovery
    from engineering_office.agent_factory import AgentFactory
    from engineering_office.capabilities import CapabilityRegistry
    (tmp_path / "mechanism.step").write_text("STEP")
    (tmp_path / "controller.kicad_sch").write_text("kicad")
    (tmp_path / "requirements.md").write_text("Design enclosure and embedded electronics")
    project = ProjectDiscovery().inspect(tmp_path, "complete engineering design")
    assert "mechanical" in project.required_domains
    assert "electronics" in project.required_domains
    agents = AgentFactory(CapabilityRegistry.default()).staff(project)
    capabilities = {c for a in agents for c in a.capabilities}
    assert {"mechanical", "electronics"} <= capabilities


def test_discovery_records_git_and_documentation_evidence(tmp_path: Path):
    import subprocess
    from engineering_office.discovery import ProjectDiscovery
    (tmp_path / "README.md").write_text("hello")
    (tmp_path / "docs").mkdir(); (tmp_path / "docs" / "architecture.md").write_text("design")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    project = ProjectDiscovery().inspect(tmp_path, "understand")
    assert project.metadata["has_docs"] is True
    assert project.metadata["git"]["is_repository"] is True
    assert "acceptance criteria" in " ".join(project.unknowns).lower()


def test_delivery_contains_architecture_and_risk_reports(tmp_path: Path):
    from engineering_office.models import ProjectMap, ProjectState, TaskContract, TaskState, Complexity, RiskLevel
    from engineering_office.storage import OfficeStore
    from engineering_office.delivery import DeliveryManager, DeliveryError
    project = ProjectMap("P1", str(tmp_path), "finish", "software", ["Python"], [], [], [], ["regression"], ["software_engineering"], [])
    store = OfficeStore(tmp_path / ".office/state.db")
    store.upsert_project(project, ProjectState.PASS)
    task = TaskContract("T1", "P1", "work", "Engineer", [], ["."], ["src"], [], ["tests pass"], [], Complexity.MEDIUM, RiskLevel.LOW)
    store.upsert_task(task, TaskState.PASS)
    (tmp_path / ".office/project.json").write_text(json.dumps({"project_type":"software","technologies":["Python"],"objective":"finish"}))
    (tmp_path / ".office/plan.json").write_text(json.dumps({"tasks":[{"task_id":"T1","owner":"Engineer","goal":"work"}]}))
    out = DeliveryManager(tmp_path, store).create("P1", {"verification":{"verdict":"PASS"}, "task_results":[], "evidence":[], "critical_risks":[]})
    assert (out / "architecture.md").exists()
    assert "Python" in (out / "architecture.md").read_text()
    assert "No unresolved critical risks" in (out / "unresolved-risks.md").read_text()


def test_delivery_rejects_unresolved_critical_risk(tmp_path: Path):
    from engineering_office.models import ProjectMap, ProjectState, TaskContract, TaskState, Complexity, RiskLevel
    from engineering_office.storage import OfficeStore
    from engineering_office.delivery import DeliveryManager, DeliveryError
    project = ProjectMap("P1", str(tmp_path), "finish", "software", [], [], [], [], [], ["software_engineering"], [])
    store = OfficeStore(tmp_path / ".office/state.db")
    store.upsert_project(project, ProjectState.PASS)
    task = TaskContract("T1", "P1", "work", "Engineer", [], ["."], ["src"], [], [], [], Complexity.MEDIUM, RiskLevel.LOW)
    store.upsert_task(task, TaskState.PASS)
    with pytest.raises(DeliveryError, match="critical"):
        DeliveryManager(tmp_path, store).create("P1", {"critical_risks":["known data loss"]})


def test_memory_tracks_agent_strength_and_weakness_tags(tmp_path: Path):
    from engineering_office.storage import OfficeStore
    from engineering_office.memory import MemoryManager
    memory = MemoryManager(OfficeStore(tmp_path / "state.db"))
    memory.record_agent_skill("Database Engineer", "locks", strong=True)
    memory.record_agent_skill("Database Engineer", "replication", strong=False)
    perf = memory.agent_performance("Database Engineer")
    assert perf["strengths"] == ["locks"]
    assert perf["weaknesses"] == ["replication"]


def test_benchmark_catalog_loads_heterogeneous_cases(tmp_path: Path):
    from engineering_office.benchmark import BenchmarkCatalog
    manifest = tmp_path / "cases.json"
    manifest.write_text(json.dumps({"cases":[
        {"case_id":"DB-1","category":"database","objective":"fix lock","expected_root_cause":"deadlock"},
        {"case_id":"ROB-1","category":"robotics","objective":"fix tf","expected_root_cause":"bad frame"}
    ]}))
    cases = BenchmarkCatalog.load(manifest).cases
    assert [c.category for c in cases] == ["database", "robotics"]


def test_git_workspace_manager_creates_isolated_task_worktree(tmp_path: Path):
    import subprocess
    from engineering_office.workspaces import GitWorkspaceManager
    repo = tmp_path / "repo"; repo.mkdir()
    subprocess.run(["git","init","-q"],cwd=repo,check=True)
    subprocess.run(["git","config","user.email","test@local.invalid"],cwd=repo,check=True)
    subprocess.run(["git","config","user.name","Test"],cwd=repo,check=True)
    (repo / "a.txt").write_text("base")
    subprocess.run(["git","add","a.txt"],cwd=repo,check=True)
    subprocess.run(["git","commit","-qm","base"],cwd=repo,check=True)
    ws = GitWorkspaceManager(repo).create("T-123")
    assert ws.path.is_dir()
    assert ws.path != repo
    assert ws.branch.startswith("office/")
    (ws.path / "a.txt").write_text("task")
    assert (repo / "a.txt").read_text() == "base"
    GitWorkspaceManager(repo).remove(ws, force=True)

from engineering_office.capabilities import CapabilityRegistry
from engineering_office.models import Complexity, ProjectState
from engineering_office.models_runtime import ModelRouter, ScriptedProvider
from engineering_office.office import OfficeEngine
from engineering_office.cli import build_parser


def test_capability_registry_covers_general_engineering_domains():
    registry = CapabilityRegistry.default()
    required = {
        "software_engineering", "systems_engineering", "research", "mathematics", "statistics",
        "machine_learning", "simulation", "robotics", "control", "electronics", "mechanical",
        "database", "security", "networking", "cloud", "frontend", "backend", "ux", "testing",
        "devops", "documentation", "benchmarking", "optimization",
    }
    assert all(registry.has(name) for name in required)


def test_cli_run_accepts_auto_without_bypassing_governance():
    args = build_parser().parse_args(["run", ".", "--auto"])
    assert args.auto is True


def test_delivery_contains_complete_reproducibility_bundle_and_marks_delivered(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    (tmp_path / "acceptance.json").write_text(json.dumps({
        "gates": [{"name": "ok", "command": "python -c \"print('ok')\"", "expected_exit": 0, "required_output": "ok"}],
        "required_evidence": [],
    }))
    engine = OfficeEngine(tmp_path)
    engine.start("verify and deliver")
    result = engine.run()
    assert result["project_state"] == "PASS"
    delivery = Path(engine.deliver())
    expected = {
        "acceptance-report.json", "test-report.json", "evidence-summary.json", "unresolved-risks.md",
        "reproducibility.md", "changes.md", "architecture.md", "project-pointer.json", "manifest.json",
    }
    assert expected <= {p.name for p in delivery.iterdir() if p.is_file()}
    assert engine.store.get_project_state(engine._load_project().project_id) is ProjectState.DELIVERED


def test_failed_candidate_is_retained_as_organizational_memory(tmp_path: Path):
    (tmp_path / "src").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "calc.py").write_text("def add(a,b):\n    return a-b\n")
    (tmp_path / "tests" / "test_calc.py").write_text("from src.calc import add\ndef test_add(): assert add(2,3)==5\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    (tmp_path / "acceptance.json").write_text(json.dumps({"gates":[{"name":"tests","command":"python -m pytest -q","expected_exit":0}],"required_evidence":[]}))
    def response(content):
        return json.dumps({"status":"COMPLETE","observations":["test fails"],"interpretations":[],"hypotheses":[],
            "actions":[{"tool":"filesystem.write","args":{"path":"src/calc.py","content":content},"reason":"candidate"}],
            "tests":[],"risks":[],"specialist_requests":[],"research_requests":[],"handoff":""})
    provider = ScriptedProvider([response("def add(a,b):\n    return a*b\n"), response("def add(a,b):\n    return a+b\n")])
    router = ModelRouter({c: provider for c in Complexity})
    engine = OfficeEngine(tmp_path, model_router=router, max_task_iterations=3)
    start = engine.start("fix")
    assert engine.run()["project_state"] == "PASS"
    memory = engine.store.list_memory(start["project"]["project_id"], verified_only=False)
    assert any(item["kind"] == "failed_attempt" for item in memory)


def test_unknown_research_project_gets_write_capable_research_specialist(tmp_path: Path):
    from engineering_office.discovery import ProjectDiscovery
    from engineering_office.agent_factory import AgentFactory
    (tmp_path / "notes.md").write_text("Investigate a new scientific mechanism and produce a report")
    project = ProjectDiscovery().inspect(tmp_path, "research and deliver findings")
    assert project.required_domains == ["research"]
    agents = AgentFactory(CapabilityRegistry.default()).staff(project)
    research = next(a for a in agents if "research" in a.capabilities)
    assert "filesystem.write" in research.allowed_tools
    assert research.write_scopes


def test_engine_exposes_independent_feedback_cycle_limit(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    engine = OfficeEngine(tmp_path, max_task_iterations=7, max_feedback_cycles=3)
    assert engine.max_task_iterations == 7
    assert engine.max_feedback_cycles == 3


def test_cli_start_accepts_model_config_and_planning_flag():
    args = build_parser().parse_args(["start", ".", "--objective", "finish", "--config", "models.json", "--plan-with-model"])
    assert args.config == "models.json"
    assert args.plan_with_model is True


def test_zip_intake_rejects_uncompressed_size_limit(tmp_path: Path):
    archive = tmp_path / "large.zip"
    make_zip(archive, {"repo/data.txt": "x" * 128})
    with pytest.raises(IntakeError, match="uncompressed"):
        ProjectIntake(max_uncompressed_bytes=64).from_zip(archive, tmp_path / "workspace")


def test_rejected_hypothesis_is_retained_before_retry(tmp_path: Path):
    (tmp_path / "src").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "src" / "calc.py").write_text("def add(a,b):\n    return a-b\n")
    (tmp_path / "tests" / "test_calc.py").write_text("from src.calc import add\ndef test_add(): assert add(2,3)==5\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    (tmp_path / "acceptance.json").write_text(json.dumps({"gates":[{"name":"tests","command":"python -m pytest -q","expected_exit":0}],"required_evidence":[]}))
    bad = json.dumps({"status":"COMPLETE","observations":["test fails"],"interpretations":[],"hypotheses":[],
        "actions":[{"tool":"filesystem.write","args":{"path":"tests/test_calc.py","content":"def test_add(): assert True\n"},"reason":"mask failure"}],
        "tests":[],"risks":[],"specialist_requests":[],"research_requests":[],"handoff":""})
    good = json.dumps({"status":"COMPLETE","observations":["implementation subtracts"],"interpretations":[],"hypotheses":[],
        "actions":[{"tool":"filesystem.write","args":{"path":"src/calc.py","content":"def add(a,b):\n    return a+b\n"},"reason":"correct implementation"}],
        "tests":[],"risks":[],"specialist_requests":[],"research_requests":[],"handoff":""})
    provider=ScriptedProvider([bad,good]); router=ModelRouter({c:provider for c in Complexity})
    engine=OfficeEngine(tmp_path,model_router=router,max_task_iterations=3,max_feedback_cycles=6)
    start=engine.start("fix without weakening tests")
    assert engine.run()["project_state"] == "PASS"
    memory=engine.store.list_memory(start["project"]["project_id"],verified_only=False)
    assert any(item["kind"] == "rejected_hypothesis" for item in memory)
