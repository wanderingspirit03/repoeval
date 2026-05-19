from __future__ import annotations

from repoeval.models import EvalTask
from repoeval.runners.mock import MockRunner


def test_mock_runner_creates_expected_files_and_log(tmp_path):
    task = EvalTask(
        id="task-1",
        name="Create files",
        category="feature",
        prompt="Create expected files",
        expected_files=["src/example.py", "README.md"],
    )
    log_path = tmp_path / "logs" / "mock.log"

    result = MockRunner().run(task, tmp_path, log_path)

    assert result.exit_code == 0
    assert result.cost_usd == 0
    assert result.stdout_path == log_path
    assert result.stderr_path.exists()
    assert "mock runner completed" in log_path.read_text(encoding="utf-8")
    assert (tmp_path / "src" / "example.py").exists()
    assert (tmp_path / "README.md").exists()


def test_mock_runner_can_return_deterministic_failure(tmp_path):
    task = EvalTask(
        id="task-1",
        name="Fail deterministically",
        category="bugfix",
        prompt="This should fail",
        metadata={"mock_fail": True},
    )
    log_path = tmp_path / "logs" / "mock.log"

    result = MockRunner().run(task, tmp_path, log_path)

    assert result.exit_code == 1
    assert result.metadata["reason"] == "mock_fail requested"
    assert "mock runner failed" in log_path.read_text(encoding="utf-8")
