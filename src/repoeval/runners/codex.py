from __future__ import annotations

from pathlib import Path
import subprocess
import time

from repoeval.models import EvalTask, RunnerConfig, RunnerResult
from repoeval.runners.base import Runner


class CodexRunner(Runner):
    name = "codex"

    def __init__(self, config: RunnerConfig) -> None:
        self.config = config

    def run(self, task: EvalTask, repo_path: Path, log_path: Path) -> RunnerResult:
        started = time.monotonic()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path = log_path.with_suffix(".err")
        command = [self.config.command or "codex", *self.config.args, task.prompt]
        env = self.config.env or None

        try:
            completed = subprocess.run(
                command,
                cwd=repo_path,
                timeout=self.config.timeout_seconds,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            exit_code = completed.returncode
            metadata = {"command": command, "timed_out": False}
        except subprocess.TimeoutExpired as exc:
            stdout = _to_text(exc.output)
            stderr = _to_text(exc.stderr)
            exit_code = 124
            metadata = {"command": command, "timed_out": True, "timeout_seconds": self.config.timeout_seconds}

        log_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        return RunnerResult(
            exit_code=exit_code,
            runtime_seconds=time.monotonic() - started,
            stdout_path=log_path,
            stderr_path=stderr_path,
            metadata=metadata,
        )


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
