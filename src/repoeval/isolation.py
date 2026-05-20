from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Literal


@dataclass
class IsolatedRepo:
    path: Path
    log_dir: Path
    _worktree: bool = False

    def cleanup(self) -> None:
        if not self.path.exists():
            return
        if self._worktree:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(self.path)],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        else:
            shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self) -> IsolatedRepo:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        self.cleanup()


def create_isolated_repo(
    repo_root: Path,
    runs_dir: Path,
    task_id: str,
    runner_name: str,
    mode: Literal["worktree", "temp-copy"],
    checkout_ref: str = "HEAD",
) -> IsolatedRepo:
    repo_root = repo_root.resolve()
    runs_dir = runs_dir.resolve()
    run_name = f"{_safe_name(task_id)}-{_safe_name(runner_name)}"
    run_root = runs_dir / run_name
    repo_path = run_root / "repo"
    log_dir = run_root / "logs"

    if run_root.exists():
        shutil.rmtree(run_root)
    log_dir.mkdir(parents=True, exist_ok=True)

    if mode == "worktree":
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(repo_path), checkout_ref],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return IsolatedRepo(path=repo_path, log_dir=log_dir, _worktree=True)

    if mode == "temp-copy":
        _copy_tracked_files(repo_root, repo_path, checkout_ref=checkout_ref)
        return IsolatedRepo(path=repo_path, log_dir=log_dir)

    raise ValueError(f"Unsupported isolation mode: {mode}")


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "_.-" else "-" for char in value)


def _copy_tracked_files(repo_root: Path, destination: Path, checkout_ref: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", checkout_ref],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    for relative in completed.stdout.splitlines():
        path = Path(relative)
        if _excluded(path):
            continue
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        blob = subprocess.run(
            ["git", "show", f"{checkout_ref}:{relative}"],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        target.write_bytes(blob.stdout)

    subprocess.run(
        ["git", "init"],
        cwd=destination,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    subprocess.run(
        ["git", "add", "."],
        cwd=destination,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=repoeval@example.invalid",
            "-c",
            "user.name=RepoEval",
            "commit",
            "--allow-empty",
            "-m",
            "baseline",
        ],
        cwd=destination,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _excluded(path: Path) -> bool:
    parts = path.parts
    if not parts:
        return False
    if parts[0] in {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".venv",
        "venv",
        "build",
        "dist",
        "__pycache__",
    }:
        return True
    if len(parts) >= 3 and parts[0] == ".repoeval" and parts[1] in {"results", "runs"}:
        return True
    return any(part == "__pycache__" for part in parts)
