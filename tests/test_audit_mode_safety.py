from pathlib import Path
import pytest


def test_policy_allows_read_search_and_safe_tests():
    from engineering_office.fast_audit import AuditModePolicy
    p = AuditModePolicy("fast-audit")
    assert p.authorize("filesystem.read", {"path":"src/a.py"})[0]
    assert p.authorize("filesystem.search", {"query":"foo"})[0]
    assert p.authorize("shell", {"command":"python -m pytest -q"})[0]
    assert p.authorize("shell", {"command":"colcon build --packages-select demo"})[0]


def test_policy_denies_source_writes_git_mutation_and_acceptance_changes():
    from engineering_office.fast_audit import AuditModePolicy
    p = AuditModePolicy("check-report")
    assert not p.authorize("filesystem.write", {"path":"src/a.py"})[0]
    assert not p.authorize("filesystem.replace_text", {"path":"acceptance.json"})[0]
    assert not p.authorize("git", {"command":"commit -am bad"})[0]
    assert not p.authorize("shell", {"command":"rm -f src/a.py"})[0]
    assert not p.authorize("shell", {"command":"sed -i 's/a/b/' src/a.py"})[0]


def test_policy_allows_office_outputs_and_readonly_git():
    from engineering_office.fast_audit import AuditModePolicy
    p = AuditModePolicy("fast-audit")
    assert p.authorize("filesystem.write", {"path":".office/reports/R1/findings.json"})[0]
    assert p.authorize("git", {"command":"status --short"})[0]
    assert p.authorize("git", {"command":"diff -- src/a.py"})[0]


def test_registry_enforces_audit_policy(tmp_path: Path):
    from engineering_office.fast_audit import AuditModePolicy
    from engineering_office.tools import FileWriteTool, ToolRegistry
    from engineering_office.security import PermissionSet, SecurityError
    reg=ToolRegistry(authorization=AuditModePolicy("fast-audit").authorize)
    reg.register(FileWriteTool(tmp_path, PermissionSet(read_scopes=["."], write_scopes=["."])))
    with pytest.raises(SecurityError): reg.execute("filesystem.write", {"path":"src/a.py","content":"x"})
