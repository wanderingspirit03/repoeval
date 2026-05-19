from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from typer.testing import CliRunner

from repoeval.cli import app
from repoeval.models import DiffStats, ExpectedFileResult, RunnerResult, VerifyResult
from repoeval.scoring import append_result, build_run_result


def test_init_creates_config(tmp_path):
    runner = CliRunner()
    result = runner.invoke(app, ["init", "--path", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".repoeval" / "tasks.yaml").read_text() == "tasks: []\n"


def test_report_command_writes_report_and_routing(tmp_path):
    result_record = build_run_result(
        task_id="task-1",
        task_name="Task 1",
        task_type="feature",
        runner="mock",
        started_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ended_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        setup=[],
        runner_result=RunnerResult(
            exit_code=0,
            runtime_seconds=1.0,
            stdout_path=Path("logs/runner.out"),
            stderr_path=Path("logs/runner.err"),
        ),
        verify=[
            VerifyResult(
                command="pytest",
                exit_code=0,
                runtime_seconds=0.5,
                stdout_path=Path("logs/pytest.out"),
                stderr_path=Path("logs/pytest.err"),
                passed=True,
            )
        ],
        diff=DiffStats(files_touched=["src/app.py"], files_modified=1, changed_lines=2, insertions=2),
        expected_files=[ExpectedFileResult(path="src/app.py", exists=True)],
        log_path=Path("logs/task-1.log"),
    )
    results_path = tmp_path / ".repoeval" / "results" / "results.jsonl"
    append_result(results_path, result_record)

    runner = CliRunner()
    cli_result = runner.invoke(
        app,
        ["report", "--results", str(results_path), "--output-dir", str(tmp_path / ".repoeval")],
    )

    assert cli_result.exit_code == 0
    assert (tmp_path / ".repoeval" / "report.md").exists()
    assert (tmp_path / ".repoeval" / "routing.yaml").exists()
    assert "Wrote" in cli_result.output
