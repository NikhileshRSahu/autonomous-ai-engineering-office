from pathlib import Path
import os
import pytest

from engineering_office.security import ApprovalPolicy, PermissionSet, SecurityError
from engineering_office.tools import FileReadTool, FileWriteTool, ReplaceTextTool, ShellTool, ToolRegistry


def perms(**kw):
    return PermissionSet(read_scopes=kw.get("read_scopes", ["."]), write_scopes=kw.get("write_scopes", ["src"]), approved_risks=kw.get("approved_risks", []))


def test_file_tool_rejects_dotdot_escape(tmp_path: Path):
    project = tmp_path / "project"; project.mkdir()
    outside = tmp_path / "secret.txt"; outside.write_text("secret")
    with pytest.raises(SecurityError):
        FileReadTool(project, perms()).execute({"path": "../secret.txt"})


def test_file_tool_rejects_symlink_escape(tmp_path: Path):
    project = tmp_path / "project"; project.mkdir()
    outside = tmp_path / "outside"; outside.mkdir(); (outside / "x.txt").write_text("x")
    try:
        os.symlink(outside, project / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink unavailable")
    with pytest.raises(SecurityError):
        FileReadTool(project, perms()).execute({"path": "link/x.txt"})


def test_write_scope_is_enforced(tmp_path: Path):
    (tmp_path / "src").mkdir(); (tmp_path / "tests").mkdir()
    tool = FileWriteTool(tmp_path, perms(write_scopes=["src"]))
    tool.execute({"path":"src/a.txt","content":"ok"})
    assert (tmp_path / "src/a.txt").read_text() == "ok"
    with pytest.raises(SecurityError):
        tool.execute({"path":"tests/a.txt","content":"no"})


def test_high_risk_shell_requires_approval_even_in_auto(tmp_path: Path):
    policy = ApprovalPolicy(auto_mode=True)
    tool = ShellTool(tmp_path, perms(write_scopes=["."]), policy=policy)
    with pytest.raises(SecurityError, match="approval"):
        tool.execute({"command":"git push origin main"})


def test_safe_shell_runs_and_mutation_is_audited(tmp_path: Path):
    events=[]
    tool = ShellTool(tmp_path, perms(write_scopes=["."]), policy=ApprovalPolicy(), audit=lambda k,d: events.append((k,d)))
    result = tool.execute({"command":"python -c \"print('ok')\""})
    assert result.ok and result.stdout.strip() == "ok"
    ReplaceTextTool(tmp_path, perms(write_scopes=["."]), audit=lambda k,d: events.append((k,d))).execute(
        {"path":"a.txt","old":"","new":"hello","create_if_missing":True}
    )
    assert any(k == "tool.mutation" for k,_ in events)


def test_registry_rejects_unknown_tool(tmp_path: Path):
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        registry.execute("not-real", {})


def test_python_write_invalidates_matching_bytecode_cache(tmp_path: Path):
    src = tmp_path / "src"; src.mkdir()
    module = src / "sample.py"; module.write_text("VALUE = 1\n")
    import subprocess, sys
    subprocess.run([sys.executable, "-c", "import sample"], cwd=src, check=True)
    cache = src / "__pycache__"
    assert list(cache.glob("sample.*.pyc"))
    FileWriteTool(tmp_path, perms(write_scopes=["src"])).execute({"path":"src/sample.py","content":"VALUE = 2\n"})
    assert not list(cache.glob("sample.*.pyc"))
