from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import Complexity, ProjectMap, ProjectState, RiskLevel, TaskContract, TaskState, dataclass_to_jsonable


class OfficeStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, state TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, task_id TEXT,
                    kind TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, task_id TEXT,
                    sender TEXT NOT NULL, recipient TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, kind TEXT NOT NULL,
                    data TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS agent_metrics (
                    agent_name TEXT PRIMARY KEY, tasks INTEGER NOT NULL DEFAULT 0,
                    verified_successes INTEGER NOT NULL DEFAULT 0, false_passes INTEGER NOT NULL DEFAULT 0,
                    total_iterations INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    def upsert_project(self, project: ProjectMap, state: ProjectState) -> None:
        data = json.dumps(dataclass_to_jsonable(project), sort_keys=True)
        with self._connect() as con:
            con.execute(
                "INSERT INTO projects(project_id,state,data) VALUES(?,?,?) "
                "ON CONFLICT(project_id) DO UPDATE SET state=excluded.state,data=excluded.data",
                (project.project_id, state.value, data),
            )

    def get_project(self, project_id: str) -> ProjectMap:
        with self._connect() as con:
            row = con.execute("SELECT data FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if not row:
            raise KeyError(project_id)
        return ProjectMap(**json.loads(row["data"]))

    def get_project_state(self, project_id: str) -> ProjectState:
        with self._connect() as con:
            row = con.execute("SELECT state FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if not row:
            raise KeyError(project_id)
        return ProjectState(row["state"])

    def set_project_state(self, project_id: str, state: ProjectState) -> None:
        with self._connect() as con:
            cur = con.execute("UPDATE projects SET state=? WHERE project_id=?", (state.value, project_id))
            if cur.rowcount == 0:
                raise KeyError(project_id)

    def upsert_task(self, task: TaskContract, state: TaskState) -> None:
        data = json.dumps(dataclass_to_jsonable(task), sort_keys=True)
        with self._connect() as con:
            con.execute(
                "INSERT INTO tasks(task_id,project_id,state,data) VALUES(?,?,?,?) "
                "ON CONFLICT(task_id) DO UPDATE SET state=excluded.state,data=excluded.data",
                (task.task_id, task.project_id, state.value, data),
            )

    def get_task(self, task_id: str) -> TaskContract:
        with self._connect() as con:
            row = con.execute("SELECT data FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        d = json.loads(row["data"])
        d["complexity"] = Complexity(d["complexity"])
        d["risk"] = RiskLevel(d["risk"])
        return TaskContract(**d)

    def get_task_state(self, task_id: str) -> TaskState:
        with self._connect() as con:
            row = con.execute("SELECT state FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        return TaskState(row["state"])

    def set_task_state(self, task_id: str, state: TaskState) -> None:
        with self._connect() as con:
            cur = con.execute("UPDATE tasks SET state=? WHERE task_id=?", (state.value, task_id))
            if cur.rowcount == 0:
                raise KeyError(task_id)

    def list_tasks(self, project_id: str) -> list[tuple[TaskContract, TaskState]]:
        with self._connect() as con:
            rows = con.execute("SELECT task_id,state FROM tasks WHERE project_id=? ORDER BY task_id", (project_id,)).fetchall()
        return [(self.get_task(r["task_id"]), TaskState(r["state"])) for r in rows]


    def delete_tasks(self, project_id: str) -> None:
        with self._connect() as con:
            con.execute("DELETE FROM tasks WHERE project_id=?", (project_id,))

    def add_event(self, project_id: str, task_id: str | None, kind: str, data: dict[str, Any]) -> int:
        with self._connect() as con:
            cur = con.execute(
                "INSERT INTO events(project_id,task_id,kind,data) VALUES(?,?,?,?)",
                (project_id, task_id, kind, json.dumps(data, sort_keys=True)),
            )
            return int(cur.lastrowid)

    def list_events(self, project_id: str) -> list[dict[str, Any]]:
        with self._connect() as con:
            rows = con.execute("SELECT * FROM events WHERE project_id=? ORDER BY id", (project_id,)).fetchall()
        return [dict(r) | {"data": json.loads(r["data"])} for r in rows]

    def add_message(self, project_id: str, task_id: str | None, sender: str, recipient: str, kind: str, data: dict[str, Any]) -> int:
        with self._connect() as con:
            cur = con.execute(
                "INSERT INTO messages(project_id,task_id,sender,recipient,kind,data) VALUES(?,?,?,?,?,?)",
                (project_id, task_id, sender, recipient, kind, json.dumps(data, sort_keys=True)),
            )
            return int(cur.lastrowid)

    def list_messages(self, project_id: str, task_id: str | None = None) -> list[dict[str, Any]]:
        sql="SELECT * FROM messages WHERE project_id=?"; args=[project_id]
        if task_id is not None:
            sql += " AND task_id=?"; args.append(task_id)
        sql += " ORDER BY id"
        with self._connect() as con:
            rows=con.execute(sql,args).fetchall()
        out=[]
        for row in rows:
            item=dict(row); item["data"]=json.loads(item["data"]); out.append(item)
        return out

    def add_memory(self, project_id: str | None, kind: str, data: dict[str, Any], verified: bool) -> int:
        with self._connect() as con:
            cur = con.execute(
                "INSERT INTO memory(project_id,kind,data,verified) VALUES(?,?,?,?)",
                (project_id, kind, json.dumps(data, sort_keys=True), int(verified)),
            )
            return int(cur.lastrowid)

    def get_memory(self, memory_id: int) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM memory WHERE id=?", (memory_id,)).fetchone()
        if not row:
            raise KeyError(memory_id)
        result = dict(row)
        result["data"] = json.loads(result["data"])
        result["verified"] = bool(result["verified"])
        return result

    def list_memory(self, project_id: str | None = None, verified_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM memory WHERE 1=1"
        args: list[Any] = []
        if project_id is not None:
            sql += " AND project_id=?"
            args.append(project_id)
        if verified_only:
            sql += " AND verified=1"
        sql += " ORDER BY id"
        with self._connect() as con:
            rows = con.execute(sql, args).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["data"] = json.loads(item["data"])
            item["verified"] = bool(item["verified"])
            out.append(item)
        return out

    def record_agent_outcome(self, agent_name: str, verified_success: bool, false_pass: bool, iterations: int) -> None:
        with self._connect() as con:
            con.execute(
                "INSERT INTO agent_metrics(agent_name,tasks,verified_successes,false_passes,total_iterations) VALUES(?,?,?,?,?) "
                "ON CONFLICT(agent_name) DO UPDATE SET "
                "tasks=tasks+1, verified_successes=verified_successes+excluded.verified_successes, "
                "false_passes=false_passes+excluded.false_passes, total_iterations=total_iterations+excluded.total_iterations",
                (agent_name, 1, int(verified_success), int(false_pass), iterations),
            )

    def get_agent_metrics(self, agent_name: str) -> dict[str, Any]:
        with self._connect() as con:
            row = con.execute("SELECT * FROM agent_metrics WHERE agent_name=?", (agent_name,)).fetchone()
        if not row:
            return {"agent_name": agent_name, "tasks": 0, "verified_successes": 0, "false_passes": 0, "average_iterations": 0.0}
        result = dict(row)
        result["average_iterations"] = result["total_iterations"] / result["tasks"] if result["tasks"] else 0.0
        return result
