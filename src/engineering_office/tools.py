from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
import subprocess

from .security import ApprovalPolicy, PathGuard, PermissionSet, SecurityError, classify_command

AuditFn = Callable[[str, dict[str, Any]], None]


def _invalidate_python_bytecode(path: Path) -> None:
    if path.suffix != ".py":
        return
    cache = path.parent / "__pycache__"
    if not cache.is_dir():
        return
    for compiled in cache.glob(f"{path.stem}.*.pyc"):
        try:
            compiled.unlink()
        except FileNotFoundError:
            pass


@dataclass(slots=True)
class ToolResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    data: dict[str, Any] | None = None
    returncode: int = 0


class BaseTool:
    name = "base"
    def __init__(self, root: str | Path, permissions: PermissionSet, audit: AuditFn | None = None):
        self.root = Path(root).resolve()
        self.permissions = permissions
        self.guard = PathGuard(self.root)
        self.audit = audit or (lambda _k, _d: None)

    def execute(self, args: dict[str, Any]) -> ToolResult:
        raise NotImplementedError


class FileReadTool(BaseTool):
    name = "filesystem.read"
    def execute(self, args: dict[str, Any]) -> ToolResult:
        path = self.guard.resolve(str(args["path"]), self.permissions.read_scopes)
        if not path.is_file():
            raise FileNotFoundError(path)
        max_bytes = int(args.get("max_bytes", 1_000_000))
        text = path.read_bytes()[:max_bytes].decode(args.get("encoding", "utf-8"), errors="replace")
        rel = str(path.relative_to(self.root))
        self.audit("file.read", {"tool": self.name, "path": rel, "bytes": len(text.encode())})
        return ToolResult(True, stdout=text, data={"path": rel, "bytes": len(text.encode())})


class FileSearchTool(BaseTool):
    name = "filesystem.search"
    def execute(self, args: dict[str, Any]) -> ToolResult:
        needle = str(args["query"])
        scope = str(args.get("scope", "."))
        base = self.guard.resolve(scope, self.permissions.read_scopes)
        matches=[]
        max_results = int(args.get("max_results", 100))
        for p in base.rglob("*"):
            if len(matches) >= max_results: break
            if not p.is_file() or p.stat().st_size > 2_000_000: continue
            try: text = p.read_text(errors="ignore")
            except OSError: continue
            for i, line in enumerate(text.splitlines(), 1):
                if needle.lower() in line.lower():
                    matches.append({"path": str(p.relative_to(self.root)), "line": i, "text": line[:500]})
                    if len(matches) >= max_results: break
        self.audit("tool.finished", {"tool": self.name, "query": needle, "scope": scope, "matches": len(matches)})
        return ToolResult(True, stdout="\n".join(f"{m['path']}:{m['line']}:{m['text']}" for m in matches), data={"matches": matches})


class FileWriteTool(BaseTool):
    name = "filesystem.write"
    def execute(self, args: dict[str, Any]) -> ToolResult:
        path = self.guard.resolve(str(args["path"]), self.permissions.write_scopes, for_write=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = str(args.get("content", ""))
        path.write_text(content, encoding=str(args.get("encoding", "utf-8")))
        _invalidate_python_bytecode(path)
        rel = str(path.relative_to(self.root))
        self.audit("file.written", {"tool": self.name, "path": rel, "bytes": len(content.encode())})
        self.audit("tool.mutation", {"tool": self.name, "path": rel, "bytes": len(content.encode())})
        return ToolResult(True, data={"path": rel, "bytes": len(content.encode())})


class ReplaceTextTool(BaseTool):
    name = "filesystem.replace_text"
    def execute(self, args: dict[str, Any]) -> ToolResult:
        path = self.guard.resolve(str(args["path"]), self.permissions.write_scopes, for_write=True)
        old, new = str(args.get("old", "")), str(args.get("new", ""))
        if not path.exists():
            if not args.get("create_if_missing", False): raise FileNotFoundError(path)
            text = ""
        else:
            text = path.read_text()
        count = int(args.get("count", -1))
        if old and old not in text:
            raise ValueError("old text not found")
        if old == "" and text and args.get("create_if_missing", False):
            raise ValueError("refusing empty-text replacement on existing non-empty file")
        updated = new if old == "" else text.replace(old, new, count)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated)
        _invalidate_python_bytecode(path)
        rel = str(path.relative_to(self.root))
        self.audit("file.written", {"tool": self.name, "path": rel, "changed": updated != text})
        self.audit("tool.mutation", {"tool": self.name, "path": rel, "changed": updated != text})
        return ToolResult(True, data={"path": rel, "changed": updated != text})


class ShellTool(BaseTool):
    name = "shell"
    def __init__(self, root: str | Path, permissions: PermissionSet, policy: ApprovalPolicy | None = None, audit: AuditFn | None = None):
        super().__init__(root, permissions, audit)
        self.policy = policy or ApprovalPolicy()

    def execute(self, args: dict[str, Any]) -> ToolResult:
        command = str(args["command"])
        risk = classify_command(command)
        if not self.policy.allows(command, risk):
            raise SecurityError(f"explicit approval required for risk={risk}: {command}")
        timeout = int(args.get("timeout", 120))
        self.audit("command.started", {"tool": self.name, "command": command, "risk": risk, "timeout": timeout})
        proc = subprocess.run(command, cwd=self.root, shell=True, text=True, capture_output=True, timeout=timeout)
        if proc.stdout or proc.stderr:
            self.audit("command.output", {"tool": self.name, "stdout": proc.stdout[-12000:], "stderr": proc.stderr[-12000:]})
        self.audit("command.finished", {"tool": self.name, "command": command, "risk": risk, "returncode": proc.returncode})
        if risk != "low" or self._looks_mutating(command):
            self.audit("tool.mutation", {"tool": self.name, "command": command, "risk": risk, "returncode": proc.returncode})
        return ToolResult(proc.returncode == 0, proc.stdout, proc.stderr, {"risk": risk}, proc.returncode)

    @staticmethod
    def _looks_mutating(command: str) -> bool:
        c = command.lower()
        return any(x in c for x in ["git commit", "pip install", "npm install", "mkdir ", "touch ", "mv ", "cp "])


class GitTool(ShellTool):
    name = "git"
    def execute(self, args: dict[str, Any]) -> ToolResult:
        subcommand = str(args["command"]).strip()
        if subcommand.startswith("git "):
            command = subcommand
        else:
            command = "git " + subcommand
        return super().execute({**args, "command": command})


class ToolRegistry:
    def __init__(self, authorization: Callable[[str, dict[str, Any]], tuple[bool, str | None]] | None = None):
        self._tools: dict[str, BaseTool] = {}
        self.authorization = authorization

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        if self.authorization is not None:
            allowed, reason = self.authorization(name, args)
            if not allowed:
                raise SecurityError(reason or f"tool not authorized in current mode: {name}")
        return self._tools[name].execute(args)

    def names(self) -> list[str]:
        return sorted(self._tools)
