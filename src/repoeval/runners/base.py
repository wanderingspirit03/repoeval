from __future__ import annotations

from pathlib import Path
from typing import Protocol

from repoeval.models import EvalTask, RunnerResult


class Runner(Protocol):
    name: str

    def run(self, task: EvalTask, repo_path: Path, log_path: Path) -> RunnerResult:
        """Run an eval task against an isolated repo and capture logs."""
