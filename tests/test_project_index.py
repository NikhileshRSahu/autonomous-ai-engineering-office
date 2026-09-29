from __future__ import annotations

import os
from pathlib import Path


def test_first_index_and_unchanged_reuse(tmp_path: Path):
    from engineering_office.project_index import ProjectIndex
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "a.py").write_text("x=1\n")
    (tmp_path / "README.md").write_text("hello")
    idx = ProjectIndex(tmp_path)
    first = idx.update()
    assert set(first.changed) == {"README.md", "src/a.py"}
    assert first.unchanged == []
    second = idx.update()
    assert second.changed == []
    assert set(second.unchanged) == {"README.md", "src/a.py"}
    assert second.generation == first.generation + 1


def test_same_size_same_mtime_content_change_invalidates(tmp_path: Path):
    from engineering_office.project_index import ProjectIndex
    path = tmp_path / "a.txt"; path.write_text("AAAA")
    idx = ProjectIndex(tmp_path); idx.update()
    stat = path.stat()
    path.write_text("BBBB")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    update = idx.update()
    assert update.changed == ["a.txt"]


def test_removed_and_default_exclusions_are_recorded(tmp_path: Path):
    from engineering_office.project_index import ProjectIndex
    (tmp_path / "keep.py").write_text("pass\n")
    (tmp_path / ".git").mkdir(); (tmp_path / ".git" / "x").write_text("no")
    (tmp_path / ".office").mkdir(); (tmp_path / ".office" / "secret").write_text("no")
    (tmp_path / "__pycache__").mkdir(); (tmp_path / "__pycache__" / "a.pyc").write_bytes(b"x")
    idx = ProjectIndex(tmp_path)
    first = idx.update()
    assert first.changed == ["keep.py"]
    assert any(item.startswith(".git") for item in first.excluded)
    (tmp_path / "keep.py").unlink()
    second = idx.update()
    assert second.removed == ["keep.py"]


def test_corrupt_index_rebuilds_safely(tmp_path: Path):
    from engineering_office.project_index import ProjectIndex
    (tmp_path / "a.py").write_text("x=1")
    idx = ProjectIndex(tmp_path); idx.update()
    idx.db_path.write_bytes(b"not sqlite")
    rebuilt = ProjectIndex(tmp_path).update()
    assert rebuilt.changed == ["a.py"]
    assert rebuilt.rebuilt is True


def test_status_reports_generation_counts(tmp_path: Path):
    from engineering_office.project_index import ProjectIndex
    (tmp_path / "a.py").write_text("x=1")
    idx = ProjectIndex(tmp_path); update = idx.update()
    status = idx.status()
    assert status["generation"] == update.generation
    assert status["file_count"] == 1
    assert status["changed_count"] == 1


def test_analysis_cache_key_requires_all_contract_dimensions(tmp_path: Path):
    from engineering_office.project_index import IncrementalAnalysisCache
    cache = IncrementalAnalysisCache(tmp_path)
    cache.put("h1", "schema-1", "qwen", "prompt-1", {"finding": "ok"})
    assert cache.get("h1", "schema-1", "qwen", "prompt-1") == {"finding": "ok"}
    assert cache.get("h2", "schema-1", "qwen", "prompt-1") is None
    assert cache.get("h1", "schema-2", "qwen", "prompt-1") is None
    assert cache.get("h1", "schema-1", "nemotron", "prompt-1") is None
    assert cache.get("h1", "schema-1", "qwen", "prompt-2") is None
