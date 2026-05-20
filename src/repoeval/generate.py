from __future__ import annotations

from pathlib import Path
import re

from repoeval.git import collect_commit_summaries
from repoeval.models import EvalTask, TaskSource

_IGNORED_PREFIXES = (".repoeval/results/", ".repoeval/runs/", ".git/", ".pytest_cache/", ".ruff_cache/")
_IGNORED_SUFFIXES = (".pyc", ".pyo")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower()).strip("-._")
    return slug or "commit"


def _is_ignored(path: str) -> bool:
    return path.startswith(_IGNORED_PREFIXES) or path.endswith(_IGNORED_SUFFIXES)


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
                expected_files=changed_files,
                source=TaskSource(
                    type="git-history",
                    commit=commit.commit,
                    parent_commit=commit.parent_commit,
                    changed_files=changed_files,
                ),
            )
        )
    return tasks[-limit:]
