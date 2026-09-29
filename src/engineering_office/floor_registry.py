from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class FloorRegistry:
    """Small local registry of project folders opened as Office floors."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else Path.home() / ".engineering-office" / "floors.json"
        self.path = self.path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")

    def _read(self) -> list[dict[str, Any]]:
        try:
            raw = json.loads(self.path.read_text())
        except Exception:
            return []
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path", "")).strip()
            if not path or path in seen:
                continue
            seen.add(path)
            row = {
                "path": path,
                "name": str(item.get("name") or Path(path).name),
                "last_opened": float(item.get("last_opened", 0.0) or 0.0),
            }
            for key in ("source_kind", "source_name", "managed"):
                if key in item:
                    row[key] = item[key]
            out.append(row)
        return out

    def _write(self, rows: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(rows, indent=2, sort_keys=True))

    def touch(self, project_root: str | Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        root = Path(project_root).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"floor root is not a directory: {root}")
        target = str(root)
        existing = next((row for row in self._read() if row["path"] == target), {})
        rows = [row for row in self._read() if row["path"] != target]
        item = {"path": target, "name": root.name, "last_opened": time.time()}
        for key in ("source_kind", "source_name", "managed"):
            if key in existing:
                item[key] = existing[key]
            if metadata is not None and key in metadata:
                item[key] = metadata[key]
        rows.insert(0, item)
        self._write(rows[:30])
        return dict(item)

    def remove(self, project_root: str | Path) -> None:
        target = str(Path(project_root).expanduser().resolve())
        self._write([row for row in self._read() if row["path"] != target])

    def list(self, current: str | Path | None = None) -> list[dict[str, Any]]:
        current_path = str(Path(current).expanduser().resolve()) if current is not None else None
        rows = self._read()
        rows.sort(key=lambda row: row.get("last_opened", 0.0), reverse=True)
        return [dict(row) | {"current": row["path"] == current_path, "initialized": (Path(row["path"]) / ".office" / "project.json").is_file()} for row in rows]
