from __future__ import annotations

from pathlib import Path
import hashlib
import re
import subprocess

from repoeval.git import collect_commit_summaries
from repoeval.models import EvalTask, TaskSource

_IGNORED_PREFIXES = (".repoeval/results/", ".repoeval/runs/", ".git/", ".pytest_cache/", ".ruff_cache/")
_IGNORED_SUFFIXES = (".pyc", ".pyo")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower()).strip("-._")
    return slug or "commit"


def _is_ignored(path: str) -> bool:
    return path.startswith(_IGNORED_PREFIXES) or path.endswith(_IGNORED_SUFFIXES)


def _target_file_hashes(repo_root: Path, commit: str, paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in paths:
        if not _exists_in_parent(repo_root, commit, path):
            continue
        completed = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            hashes[path] = hashlib.sha256(completed.stdout).hexdigest()
    return hashes


def _paths_existing_in_commit(repo_root: Path, commit: str, paths: list[str]) -> list[str]:
    existing_paths: list[str] = []
    for path in paths:
        exists = (
            subprocess.run(
                ["git", "cat-file", "-e", f"{commit}:{path}"],
                cwd=repo_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        )
        if exists:
            existing_paths.append(path)
    return existing_paths


def _exists_in_parent(repo_root: Path, commit: str, path: str) -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", f"{commit}^"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    parent_commit = completed.stdout.strip()
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{parent_commit}:{path}"],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def generate_from_git_history(
    repo_root: Path,
    limit: int,
    since: str | None = None,
    category: str | None = None,
) -> list[EvalTask]:
    commits = collect_commit_summaries(repo_root, limit=limit, since=since)
    tasks: list[EvalTask] = []
    for commit in commits:
        changed_files = [path for path in commit.changed_files if not _is_ignored(path)]
        if not changed_files:
            continue
        expected_files = _paths_existing_in_commit(repo_root, commit.commit, changed_files)
        slug = _slugify(commit.subject)
        short_sha = commit.commit[:8]
        body = f"\n\nCommit body:\n{commit.body}" if commit.body else ""
        prompt = (
            f"Recreate the intent of git commit {short_sha}: {commit.subject}.{body}\n\n"
            "Changed files from the original commit:\n"
            + "\n".join(f"- {path}" for path in changed_files)
            + "\n\nUse the repository tests to verify the change."
        )
        tasks.append(
            EvalTask(
                id=f"git-{slug}-{short_sha}",
                name=commit.subject,
                prompt=prompt,
                task_type=category or "git-history",
                verify_commands=["pytest"],
                expected_files=expected_files,
                source=TaskSource(
                    type="git-history",
                    commit=commit.commit,
                    parent_commit=commit.parent_commit,
                    changed_files=changed_files,
                    target_file_hashes=_target_file_hashes(repo_root, commit.commit, changed_files),
                ),
            )
        )
    return tasks[-limit:]
