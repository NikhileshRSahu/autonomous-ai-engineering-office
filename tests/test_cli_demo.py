from pathlib import Path
import json

from engineering_office.cli import main
from engineering_office.integrations import ExternalCommandAgentLauncher
from engineering_office.research import ResearchManager, ResearchRequest


def test_cli_help(capsys):
    assert main(["--help"]) == 0
    assert "Autonomous AI Engineering Office" in capsys.readouterr().out


def test_doctor_reports_runtime(tmp_path: Path, capsys):
    assert main(["doctor", str(tmp_path)]) == 0
    data=json.loads(capsys.readouterr().out)
    assert data["python"]["ok"] is True
    assert data["git"]["ok"] is True


def test_start_cli_creates_office(tmp_path: Path, capsys):
    (tmp_path/"pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    (tmp_path/"tests").mkdir(); (tmp_path/"tests"/"test_x.py").write_text("def test_x(): assert True\n")
    assert main(["start",str(tmp_path),"--objective","inspect and finish"]) == 0
    out=json.loads(capsys.readouterr().out)
    assert out["project"]["objective"] == "inspect and finish"
    assert (tmp_path/".office"/"plan.json").exists()


def test_offline_demo_exercises_full_loop(tmp_path: Path, capsys):
    workspace=tmp_path/"demo"
    assert main(["demo","--workspace",str(workspace)]) == 0
    data=json.loads(capsys.readouterr().out)
    assert data["run"]["project_state"] == "PASS"
    assert data["delivery"]
    assert "return a + b" in (workspace/"src"/"calculator.py").read_text()
    assert list((workspace/".office"/"evidence").rglob("verification.json"))
    acceptance=json.loads((workspace/"acceptance.json").read_text())
    assert acceptance["gates"][0]["command"] == "python -m unittest discover -s tests -q"


def test_external_launcher_uses_template_without_shell(tmp_path: Path):
    prompt=tmp_path/"prompt.txt"; prompt.write_text("hello")
    launcher=ExternalCommandAgentLauncher("python -c \"import pathlib; print(pathlib.Path(r'{prompt}').read_text())\"")
    result=launcher.launch(tmp_path, prompt)
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"


def test_research_manager_fails_honestly_without_provider():
    manager=ResearchManager(provider=None)
    req=ResearchRequest(topic="unknown api", questions=["how?"], reason="needed")
    try:
        manager.research(req)
    except RuntimeError as exc:
        assert "no research provider" in str(exc).lower()
    else:
        raise AssertionError("expected missing provider failure")


def test_model_cli_exposes_status_switch_and_cold_start(monkeypatch, tmp_path: Path, capsys):
    class Manager:
        specs={"qwen":object(),"nemotron":object()}
        current_model=None
        def status(self,name): return {"name":name,"status":"STOPPED"}
        def ensure(self,name): self.current_model=name; return {"name":name,"status":"READY"}
        def stop(self,name): return {"name":name,"status":"STOPPED"}
        def stop_all_owned(self): return [{"name":"qwen","status":"STOPPED"}]
        def cold_start_validate(self,sequence,output_path=None):
            return {"cold_start":True,"transitions":[{"model":x,"status":"READY"} for x in sequence],"final_model":sequence[-1]}
    manager=Manager()
    class Router:
        lifecycle_manager=manager
    monkeypatch.setattr("engineering_office.cli._router_from_config", lambda config, project_root=None: Router())

    assert main(["model","status",str(tmp_path),"--config","local.json"]) == 0
    status=json.loads(capsys.readouterr().out)
    assert {x["name"] for x in status["models"]} == {"qwen","nemotron"}

    assert main(["model","switch","qwen",str(tmp_path),"--config","local.json"]) == 0
    switched=json.loads(capsys.readouterr().out)
    assert switched["status"] == "READY"

    assert main(["model","cold-start",str(tmp_path),"--config","local.json","--sequence","qwen,nemotron,qwen"]) == 0
    report=json.loads(capsys.readouterr().out)
    assert report["cold_start"] is True
    assert report["final_model"] == "qwen"
