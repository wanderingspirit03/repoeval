from __future__ import annotations

import subprocess

from repoeval.models import EvalTask, RunnerConfig
from repoeval.runners.codex import CodexRunner


class Completed:
    def __init__(self, returncode: int = 0, stdout: str = "out", stderr: str = "err") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_codex_runner_constructs_command_and_captures_logs(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, cwd, timeout, capture_output, text, env, check):
        calls.append(
            {
                "cmd": cmd,
                "cwd": cwd,
                "timeout": timeout,
                "capture_output": capture_output,
                "text": text,
                "env": env,
                "check": check,
            }
        )
        return Completed(returncode=7, stdout="codex stdout", stderr="codex stderr")

    monkeypatch.setattr(subprocess, "run", fake_run)
    task = EvalTask(id="task-1", name="Do work", category="feature", prompt="Implement feature")
    config = RunnerConfig(type="codex", command="codex", args=["exec", "--full-auto"], timeout_seconds=12, env={"X": "Y"})
    log_path = tmp_path / "logs" / "codex.log"

    result = CodexRunner(config=config).run(task, tmp_path, log_path)

    assert calls == [
        {
            "cmd": ["codex", "exec", "--full-auto", "Implement feature"],
            "cwd": tmp_path,
            "timeout": 12,
            "capture_output": True,
            "text": True,
            "env": {"X": "Y"},
            "check": False,
        }
    ]
    assert result.exit_code == 7
    assert result.stdout_path.read_text(encoding="utf-8") == "codex stdout"
    assert result.stderr_path.read_text(encoding="utf-8") == "codex stderr"
    assert result.metadata["command"] == ["codex", "exec", "--full-auto", "Implement feature"]


def test_codex_runner_records_timeout_without_requiring_codex(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["codex", "exec"], timeout=3, output="partial out", stderr="partial err")

    monkeypatch.setattr(subprocess, "run", fake_run)
    task = EvalTask(id="task-1", name="Do work", category="feature", prompt="Implement feature")
    config = RunnerConfig(type="codex", command="codex", args=["exec"], timeout_seconds=3)
    log_path = tmp_path / "logs" / "codex.log"

    result = CodexRunner(config=config).run(task, tmp_path, log_path)

    assert result.exit_code == 124
    assert result.metadata["timed_out"] is True
    assert "partial out" in result.stdout_path.read_text(encoding="utf-8")
    assert "partial err" in result.stderr_path.read_text(encoding="utf-8")
