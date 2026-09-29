from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess


@dataclass(slots=True)
class ExternalLaunchResult:
    returncode: int
    stdout: str
    stderr: str


class ExternalCommandAgentLauncher:
    """Launches OpenCode, Munder Difflin helpers, Codex-like CLIs, or other local agents via a user-supplied command template."""
    def __init__(self, command_template: str, timeout: int = 900):
        self.command_template=command_template
        self.timeout=timeout

    def launch(self, project_root: str | Path, prompt_file: str | Path) -> ExternalLaunchResult:
        project=Path(project_root).resolve(); prompt=Path(prompt_file).resolve()
        command=self.command_template.format(project=str(project), prompt=str(prompt))
        proc=subprocess.run(shlex.split(command), cwd=project, text=True, capture_output=True, timeout=self.timeout)
        return ExternalLaunchResult(proc.returncode, proc.stdout, proc.stderr)

@dataclass(slots=True)
class CommandToolResult:
    ok: bool
    stdout: str
    stderr: str
    returncode: int


class CommandToolAdapter:
    """JSON stdin/stdout adapter for project-specific browser/database/container/build tools.

    The command is an argv list and is always executed with shell=False.
    """
    def __init__(self, name: str, command: list[str], timeout: int = 120):
        if not name.strip() or not command:
            raise ValueError("adapter requires name and command argv")
        self.name=name
        self.command=list(command)
        self.timeout=timeout

    def execute(self, args: dict, project_root: str | Path) -> CommandToolResult:
        import json
        proc=subprocess.run(
            self.command, cwd=Path(project_root).resolve(), input=json.dumps(args),
            text=True, capture_output=True, timeout=self.timeout, shell=False,
        )
        return CommandToolResult(proc.returncode == 0, proc.stdout, proc.stderr, proc.returncode)


class ExtensionRegistry:
    def __init__(self):
        self._items: dict[str, CommandToolAdapter] = {}

    def register(self, adapter: CommandToolAdapter) -> None:
        if adapter.name in self._items:
            raise ValueError(f"extension already registered: {adapter.name}")
        self._items[adapter.name]=adapter

    def execute(self, name: str, args: dict, project_root: str | Path) -> CommandToolResult:
        if name not in self._items:
            raise KeyError(name)
        return self._items[name].execute(args, project_root)

    def names(self) -> list[str]:
        return sorted(self._items)
