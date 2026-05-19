from __future__ import annotations

import json
import subprocess
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from repoeval.models import (
    CommandResult,
    DiffStats,
    ExpectedFileResult,
    RunResult,
    RunnerResult,
    VerifyResult,
)


def collect_diff_stats(repo_path: Path) -> DiffStats:
    """Collect git diff statistics for uncommitted changes in a repo/worktree."""
    name_status = subprocess.run(
        ["git", "diff", "--name-status"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    numstat = subprocess.run(
        ["git", "diff", "--numstat"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    files_touched: list[str] = []
    files_added = files_modified = files_deleted = 0
    status_by_path: dict[str, str] = {}

    for raw_line in name_status.splitlines():
        if not raw_line.strip():
            continue
        parts = raw_line.split("\t")
        status = parts[0]
        path = parts[-1]
        files_touched.append(path)
        status_by_path[path] = status
        if status.startswith("A"):
            files_added += 1
        elif status.startswith("D"):
            files_deleted += 1
        else:
            files_modified += 1

    insertions = 0
    deletions = 0
    for raw_line in numstat.splitlines():
        if not raw_line.strip():
            continue
        added, deleted, path = raw_line.split("\t", maxsplit=2)
        path = path.split("\t")[-1]
        if added != "-":
            insertions += int(added)
        if deleted != "-":
            deletions += int(deleted)

    for path in untracked.splitlines():
        if not path.strip():
            continue
        files_touched.append(path)
        files_added += 1
        file_path = repo_path / path
        if file_path.is_file():
            insertions += len(file_path.read_text(encoding="utf-8", errors="ignore").splitlines())

    files_touched = sorted(set(files_touched))
    return DiffStats(
        files_touched=files_touched,
        files_added=files_added,
        files_modified=files_modified,
        files_deleted=files_deleted,
        changed_lines=insertions + deletions,
        insertions=insertions,
        deletions=deletions,
    )


def build_run_result(
    *,
    task_id: str,
    task_name: str,
    task_type: str,
    runner: str,
    started_at: datetime,
    ended_at: datetime,
    setup: Sequence[CommandResult],
    runner_result: RunnerResult,
    verify: Sequence[VerifyResult],
    diff: DiffStats,
    expected_files: Sequence[ExpectedFileResult],
    log_path: Path,
    cost_usd: Decimal | None = None,
    error: str | None = None,
) -> RunResult:
    runtime_seconds = max(0.0, (ended_at - started_at).total_seconds())
    if error is not None or runner_result.exit_code != 0:
        status = "error"
    elif any(command.exit_code != 0 for command in setup):
        status = "failed"
    elif any(not item.passed or item.exit_code != 0 for item in verify):
        status = "failed"
    elif any(not item.exists for item in expected_files):
        status = "failed"
    else:
        status = "passed"

    return RunResult(
        task_id=task_id,
        task_name=task_name,
        task_type=task_type,
        runner=runner,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        runtime_seconds=runtime_seconds,
        setup=list(setup),
        runner_result=runner_result,
        verify=list(verify),
        diff=diff,
        expected_files=list(expected_files),
        log_path=log_path,
        cost_usd=cost_usd if cost_usd is not None else runner_result.cost_usd,
        error=error,
    )


def append_result(path: Path, result: RunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(result.model_dump_json() + "\n")


def load_results(path: Path) -> list[RunResult]:
    if not path.exists():
        return []
    results: list[RunResult] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                results.append(RunResult.model_validate(json.loads(line)))
    return results
