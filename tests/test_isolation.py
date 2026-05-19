from __future__ import annotations

import subprocess
from pathlib import Path

from repoeval.isolation import create_isolated_repo


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _make_repo(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    (repo / ".repoeval" / "results").mkdir(parents=True)
    (repo / ".repoeval" / "runs").mkdir(parents=True)
    (repo / ".repoeval" / "results" / "old.jsonl").write_text("old\n", encoding="utf-8")
    (repo / ".repoeval" / "runs" / "old.log").write_text("old\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    _git(repo, "add", "tracked.txt")
    _git(repo, "commit", "-m", "initial")


def test_temp_copy_isolation_copies_tracked_files_and_excludes_run_artifacts(tmp_path):
    repo = tmp_path / "repo"
    _make_repo(repo)
    runs_dir = tmp_path / "runs"

    isolated = create_isolated_repo(repo, runs_dir, "task-1", "mock", mode="temp-copy")

    try:
        assert isolated.path != repo
        assert isolated.path.exists()
        assert isolated.log_dir.exists()
        assert (isolated.path / "tracked.txt").read_text(encoding="utf-8") == "tracked\n"
        assert not (isolated.path / ".git").exists()
        assert not (isolated.path / "untracked.txt").exists()
        assert not (isolated.path / ".repoeval" / "results" / "old.jsonl").exists()
        assert not (isolated.path / ".repoeval" / "runs" / "old.log").exists()
    finally:
        isolated.cleanup()

    assert not isolated.path.exists()


def test_isolation_starts_clean_for_each_runner_task_combination(tmp_path):
    repo = tmp_path / "repo"
    _make_repo(repo)
    runs_dir = tmp_path / "runs"

    first = create_isolated_repo(repo, runs_dir, "task-1", "mock", mode="temp-copy")
    try:
        (first.path / "scratch.txt").write_text("dirty\n", encoding="utf-8")
    finally:
        first.cleanup()

    second = create_isolated_repo(repo, runs_dir, "task-1", "mock", mode="temp-copy")
    try:
        assert not (second.path / "scratch.txt").exists()
        assert (second.path / "tracked.txt").exists()
    finally:
        second.cleanup()
