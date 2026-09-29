from pathlib import Path

from engineering_office.agent_factory import AgentFactory
from engineering_office.capabilities import CapabilityRegistry
from engineering_office.discovery import ProjectDiscovery


def test_discovery_detects_python_fastapi_postgres(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["fastapi","psycopg"]\n')
    (tmp_path / "README.md").write_text("FastAPI service backed by PostgreSQL")
    (tmp_path / "tests").mkdir()
    project = ProjectDiscovery().inspect(tmp_path, "make production ready")
    assert "Python" in project.technologies
    assert "FastAPI" in project.technologies
    assert "PostgreSQL" in project.technologies
    assert "backend" in project.required_domains
    assert "database" in project.required_domains
    assert project.metadata["has_tests"] is True


def test_agent_factory_staffs_only_relevant_domains(tmp_path: Path):
    (tmp_path / "package.json").write_text('{"dependencies":{"react":"1","express":"1"}}')
    project = ProjectDiscovery().inspect(tmp_path, "finish full stack app")
    staff = AgentFactory(CapabilityRegistry.default()).staff(project)
    names = {a.name for a in staff}
    assert any("Frontend" in n for n in names)
    assert any("Backend" in n for n in names)
    assert not any("Robotics" in n for n in names)


def test_create_narrow_specialist_from_request():
    factory = AgentFactory(CapabilityRegistry.default())
    agent = factory.create_specialist(
        expertise="PostgreSQL concurrency",
        reason="lock contention",
        write_scopes=["database", "migrations"],
        tools=["filesystem.read", "shell"],
    )
    assert "PostgreSQL" in agent.name
    assert "database" in agent.capabilities
    assert agent.write_scopes == ["database", "migrations"]
    assert "modify acceptance gates" in agent.forbidden_actions
