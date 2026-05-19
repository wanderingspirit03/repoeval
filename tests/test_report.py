from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from repoeval.models import DiffStats, ExpectedFileResult, RunnerResult, VerifyResult
from repoeval.report import summarize_results, write_report
from repoeval.scoring import build_run_result


def _result(
    *,
    task_id: str,
    task_type: str,
    runner: str,
    verify_passed: bool,
    runtime_seconds: float,
    changed_lines: int,
) :
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ended = datetime.fromtimestamp(started.timestamp() + runtime_seconds, tz=timezone.utc)
    return build_run_result(
        task_id=task_id,
        task_name=f"Task {task_id}",
        task_type=task_type,
        runner=runner,
        started_at=started,
        ended_at=ended,
        setup=[],
        runner_result=RunnerResult(
            exit_code=0,
            runtime_seconds=runtime_seconds,
            stdout_path=Path("logs/runner.out"),
            stderr_path=Path("logs/runner.err"),
        ),
        verify=[
            VerifyResult(
                command="pytest",
                exit_code=0 if verify_passed else 1,
                runtime_seconds=0.5,
                stdout_path=Path("logs/pytest.out"),
                stderr_path=Path("logs/pytest.err"),
                passed=verify_passed,
            )
        ],
        diff=DiffStats(
            files_touched=["src/app.py"],
            files_modified=1,
            changed_lines=changed_lines,
            insertions=changed_lines,
        ),
        expected_files=[ExpectedFileResult(path="src/app.py", exists=True)],
        log_path=Path(f"logs/{task_id}-{runner}.log"),
    )


def test_report_markdown_summarizes_agents_categories_and_failures(tmp_path):
    results = [
        _result(task_id="feature-1", task_type="feature", runner="mock", verify_passed=True, runtime_seconds=2.0, changed_lines=5),
        _result(task_id="bug-1", task_type="bugfix", runner="mock", verify_passed=False, runtime_seconds=4.0, changed_lines=9),
        _result(task_id="feature-1", task_type="feature", runner="codex", verify_passed=True, runtime_seconds=6.0, changed_lines=3),
    ]

    summary = summarize_results(results)
    output = tmp_path / ".repoeval" / "report.md"
    write_report(summary, output)

    text = output.read_text(encoding="utf-8")
    assert text.startswith("# RepoEval Report\n")
    assert "## By Runner" in text
    assert "| mock | 1/2 | 50.0% | 3.00 | 7.0 |" in text
    assert "| codex | 1/1 | 100.0% | 6.00 | 3.0 |" in text
    assert "## By Task Type" in text
    assert "| feature | mock | 1/1 | 100.0% | 2.00 | 5.0 |" in text
    assert "## Notable Failures" in text
    assert "bug-1" in text
    assert "logs/bug-1-mock.log" in text
