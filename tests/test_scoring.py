from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from repoeval.models import CommandResult, DiffStats, ExpectedFileResult, RunnerResult, VerifyResult
from repoeval.scoring import append_result, build_run_result, collect_diff_stats, load_results


def _command(command: str, exit_code: int = 0) -> CommandResult:
    return CommandResult(
        command=command,
        exit_code=exit_code,
        runtime_seconds=0.25,
        stdout_path=Path("logs/stdout.txt"),
        stderr_path=Path("logs/stderr.txt"),
    )


def _runner_result(exit_code: int = 0) -> RunnerResult:
    return RunnerResult(
        exit_code=exit_code,
        runtime_seconds=1.5,
        stdout_path=Path("logs/runner.out"),
        stderr_path=Path("logs/runner.err"),
    )


def test_collect_diff_stats_counts_files_and_changed_lines(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "modified.py").write_text("old\n", encoding="utf-8")
    (repo / "deleted.py").write_text("gone\n", encoding="utf-8")

    import subprocess

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True, text=True)

    (repo / "modified.py").write_text("new\nextra\n", encoding="utf-8")
    (repo / "added.py").write_text("hello\nworld\n", encoding="utf-8")
    (repo / "deleted.py").unlink()

    diff = collect_diff_stats(repo)

    assert diff.files_touched == ["added.py", "deleted.py", "modified.py"]
    assert diff.files_added == 1
    assert diff.files_modified == 1
    assert diff.files_deleted == 1
    assert diff.insertions == 4
    assert diff.deletions == 2
    assert diff.changed_lines == 6


def test_build_run_result_status_and_jsonl_round_trip(tmp_path):
    result = build_run_result(
        task_id="task-1",
        task_name="Add feature",
        task_type="feature",
        runner="mock",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
        setup=[_command("python -m pip install -e .")],
        runner_result=_runner_result(exit_code=0),
        verify=[VerifyResult(**_command("pytest", exit_code=0).model_dump(), passed=True)],
        diff=DiffStats(files_touched=["src/app.py"], files_modified=1, changed_lines=4, insertions=3, deletions=1),
        expected_files=[ExpectedFileResult(path="src/app.py", exists=True)],
        log_path=Path("logs/run.log"),
    )

    assert result.status == "passed"
    assert result.runtime_seconds == 2.0

    output = tmp_path / "results.jsonl"
    append_result(output, result)
    loaded = load_results(output)

    assert loaded == [result]
    line = output.read_text(encoding="utf-8").strip()
    assert '"schema_version":1' in line
    assert '"task_id":"task-1"' in line
    assert '"verify"' in line
    assert '"exit_code":0' in line
    assert '"log_path":"logs/run.log"' in line


def test_build_run_result_marks_failed_when_verify_or_expected_file_fails():
    result = build_run_result(
        task_id="task-1",
        task_name="Add feature",
        task_type="feature",
        runner="mock",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc),
        setup=[],
        runner_result=_runner_result(exit_code=0),
        verify=[VerifyResult(**_command("pytest", exit_code=1).model_dump(), passed=False)],
        diff=DiffStats(),
        expected_files=[ExpectedFileResult(path="src/app.py", exists=False)],
        log_path=Path("logs/run.log"),
    )

    assert result.status == "failed"
