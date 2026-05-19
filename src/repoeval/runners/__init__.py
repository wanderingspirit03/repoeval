from __future__ import annotations

from repoeval.models import RunnerConfig
from repoeval.runners.base import Runner
from repoeval.runners.codex import CodexRunner
from repoeval.runners.mock import MockRunner


def build_runner(name: str, config: RunnerConfig) -> Runner:
    if name != config.type:
        raise ValueError(f"Runner name {name!r} does not match configured type {config.type!r}")
    if config.type == "mock":
        return MockRunner()
    if config.type == "codex":
        return CodexRunner(config)
    raise ValueError(f"Unsupported runner type: {config.type}")


__all__ = ["CodexRunner", "MockRunner", "Runner", "build_runner"]
