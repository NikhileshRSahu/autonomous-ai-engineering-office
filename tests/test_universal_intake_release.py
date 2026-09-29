from __future__ import annotations

import json
from pathlib import Path

from engineering_office.config import OfficeConfig
from engineering_office.ui_service import DashboardService


def test_office_config_exposes_universal_intake_defaults():
    cfg = OfficeConfig()
    assert cfg.intake_workspace_root == "~/.engineering-office/workspaces"
    assert cfg.intake_staging_root == "~/.engineering-office/staging"
    assert cfg.intake_max_files == 100_000
    assert cfg.intake_max_bytes == 8 * 1024 * 1024 * 1024
    assert cfg.intake_session_ttl == 24 * 60 * 60


def test_office_config_loads_universal_intake_overrides(tmp_path: Path):
    path = tmp_path / "office.json"
    path.write_text(json.dumps({
        "intake_workspace_root": "/tmp/office-workspaces",
        "intake_staging_root": "/tmp/office-staging",
        "intake_max_files": 321,
        "intake_max_bytes": 654321,
        "intake_session_ttl": 1234,
    }))
    cfg = OfficeConfig.load(path)
    assert cfg.intake_workspace_root == "/tmp/office-workspaces"
    assert cfg.intake_staging_root == "/tmp/office-staging"
    assert cfg.intake_max_files == 321
    assert cfg.intake_max_bytes == 654321
    assert cfg.intake_session_ttl == 1234


def test_dashboard_default_config_surfaces_intake_limits(tmp_path: Path):
    config = DashboardService._read_config(tmp_path / "missing.json")
    assert config["intake_workspace_root"] == "~/.engineering-office/workspaces"
    assert config["intake_staging_root"] == "~/.engineering-office/staging"
    assert config["intake_max_files"] == 100_000
    assert config["intake_max_bytes"] == 8 * 1024 * 1024 * 1024
    assert config["intake_session_ttl"] == 86_400

def test_dashboard_old_config_is_backfilled_with_intake_defaults(tmp_path: Path):
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"parallelism": 9, "model_profiles": {}, "routing": {}}))
    config = DashboardService._read_config(path)
    assert config["parallelism"] == 9
    assert config["intake_workspace_root"] == "~/.engineering-office/workspaces"
    assert config["intake_max_files"] == 100_000
