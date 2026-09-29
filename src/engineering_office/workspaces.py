from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess


class WorkspaceError(RuntimeError):
    pass


@dataclass(slots=True)
class GitWorkspace:
    task_id: str
    branch: str
    path: Path


class GitWorkspaceManager:
    """Optional isolated task worktrees for substantial implementation work.

    It never merges or pushes automatically. Integration remains a separately verified action.
    """
    def __init__(self, repository: str | Path, workspace_root: str | Path | None = None):
        self.repository=Path(repository).resolve()
        if not (self.repository / ".git").exists():
            raise WorkspaceError(f"not a git repository: {self.repository}")
        default=self.repository.parent / ".office-worktrees" / self.repository.name
        self.workspace_root=Path(workspace_root).resolve() if workspace_root else default

    def create(self, task_id: str) -> GitWorkspace:
        slug=re.sub(r"[^a-zA-Z0-9._-]+","-",task_id).strip("-").lower() or "task"
        branch=f"office/{slug}"
        path=self.workspace_root / slug
        if path.exists():
            raise WorkspaceError(f"workspace already exists: {path}")
        self.workspace_root.mkdir(parents=True,exist_ok=True)
        check=subprocess.run(["git","rev-parse","--verify","HEAD"],cwd=self.repository,text=True,capture_output=True)
        if check.returncode != 0:
            raise WorkspaceError("repository requires at least one commit before creating a worktree")
        proc=subprocess.run(["git","worktree","add",str(path),"-b",branch,"HEAD"],cwd=self.repository,text=True,capture_output=True)
        if proc.returncode != 0:
            raise WorkspaceError(proc.stderr.strip() or "git worktree add failed")
        return GitWorkspace(task_id,branch,path)

    def remove(self, workspace: GitWorkspace, force: bool = False) -> None:
        args=["git","worktree","remove"]
        if force: args.append("--force")
        args.append(str(workspace.path))
        proc=subprocess.run(args,cwd=self.repository,text=True,capture_output=True)
        if proc.returncode != 0:
            raise WorkspaceError(proc.stderr.strip() or "git worktree remove failed")
        # Prune empty external parent directories created only for office worktrees.
        try:
            if self.workspace_root.exists() and not any(self.workspace_root.iterdir()):
                self.workspace_root.rmdir()
        except OSError:
            pass
