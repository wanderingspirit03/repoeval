from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from repoeval.models import DiffStats, ExpectedFileResult, RunnerResult, VerifyResult
from repoeval.routing import build_routing, write_routing
from repoeval.scoring import build_run_result


def _result(task_id: str, task_type: str, runner: str, passed: bool, runtime: float, changed_lines: int):
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ended = datetime.fromtimestamp(started.timestamp() + runtime, tz=timezone.utc)
    return build_run_result(
        task_id=task_id,
        task_name=task_id,
        task_type=task_type,
        runner=runner,
        started_at=started,
        ended_at=ended,
        setup=[],
        runner_result=RunnerResult(
            exit_code=0,
            runtime_seconds=runtime,
            stdout_path=Path("logs/runner.out"),
            stderr_path=Path("logs/runner.err"),
        ),
        verify=[
            VerifyResult(
                command="pytest",
                exit_code=0 if passed else 1,
                runtime_seconds=0.5,
                stdout_path=Path("logs/pytest.out"),
                stderr_path=Path("logs/pytest.err"),
                passed=passed,
            )
        ],
        diff=DiffStats(changed_lines=changed_lines, insertions=changed_lines),
        expected_files=[ExpectedFileResult(path="src/app.py", exists=True)],
        log_path=Path(f"logs/{task_id}-{runner}.log"),
    )


def test_routing_recommends_highest_pass_rate_then_runtime_changed_lines_and_name(tmp_path):
    results = [
        _result("feature-1", "feature", "codex", True, 10.0, 4),
        _result("feature-2", "feature", "codex", False, 4.0, 2),
        _result("feature-1", "feature", "mock", True, 5.0, 6),
        _result("feature-2", "feature", "mock", True, 7.0, 8),
        _result("docs-1", "docs", "zeta", True, 3.0, 5),
        _result("docs-1", "docs", "alpha", True, 3.0, 5),
    ]

    recommendations = build_routing(results)

    feature = next(item for item in recommendations if item.task_type == "feature")
    assert feature.recommended_runner == "mock"
    assert feature.pass_rate == 1.0
    assert feature.median_runtime_seconds == 6.0
    assert feature.median_changed_lines == 7
    assert feature.sample_size == 2
    assert feature.alternatives == ["codex"]

    docs = next(item for item in recommendations if item.task_type == "docs")
    assert docs.recommended_runner == "alpha"
    assert docs.alternatives == ["zeta"]

    output = tmp_path / ".repoeval" / "routing.yaml"
    write_routing(output, recommendations)
    data = yaml.safe_load(output.read_text(encoding="utf-8"))

    assert data["version"] == 1
    assert data["routes"]["feature"]["recommended_runner"] == "mock"
    assert data["routes"]["docs"]["recommended_runner"] == "alpha"
