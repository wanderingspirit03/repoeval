from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import subprocess

from repoeval.models import DiffStats


@dataclass(frozen=True)
class GitCommitSummary:
    commit: str
    parent_commit: str | None
    subject: str
    body: str
    changed_files: list[str]


def run_git(repo_root: Path, args: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def collect_commit_summaries(
    repo_root: Path,
    limit: int,
    since: str | None = None,
) -> list[GitCommitSummary]:
    args = [
        "log",
        "--reverse",
        f"--max-count={limit}",
        "--format=%x1e%H%x1f%P%x1f%s%x1f%b",
        "--name-only",
    ]
    if since:
        args.append(f"{since}..HEAD")
    try:
        output = run_git(repo_root, args)
    except subprocess.CalledProcessError:
        return []
    if not output.strip():
        return []

    commits: list[GitCommitSummary] = []
    for raw_record in output.split("\x1e"):
        record = raw_record.strip("\n")
        if not record.strip():
            continue
        lines = record.splitlines()
        header = lines[0].split("\x1f")
        if len(header) != 4:
            continue
        commit, parents, subject, body = header
        parent_parts = parents.split()
        if len(parent_parts) > 1:
            continue
        changed_files = [line.strip() for line in lines[1:] if line.strip()]
        commits.append(
            GitCommitSummary(
                commit=commit,
                parent_commit=parent_parts[0] if parent_parts else None,
                subject=subject.strip(),
                body=body.strip(),
                changed_files=changed_files,
            )
        )
    return commits


def diff_stats(repo_root: Path, base_ref: str, head_ref: str | None = None) -> DiffStats:
    refspec = f"{base_ref}..{head_ref}" if head_ref else base_ref
    output = run_git(repo_root, ["diff", "--numstat", "--name-status", refspec])
    files_touched: list[str] = []
    insertions = 0
    deletions = 0
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
            insertions += int(parts[0])
            deletions += int(parts[1])
            files_touched.append(parts[2])
    return DiffStats(
        files_touched=files_touched,
        changed_lines=insertions + deletions,
        insertions=insertions,
        deletions=deletions,
    )
