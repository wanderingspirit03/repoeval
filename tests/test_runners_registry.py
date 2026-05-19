from __future__ import annotations

import pytest

from repoeval.models import RunnerConfig
from repoeval.runners import build_runner
from repoeval.runners.codex import CodexRunner
from repoeval.runners.mock import MockRunner


def test_build_runner_returns_configured_runner():
    assert isinstance(build_runner("mock", RunnerConfig(type="mock")), MockRunner)
    assert isinstance(build_runner("codex", RunnerConfig(type="codex", command="codex", args=["exec"])), CodexRunner)


def test_build_runner_rejects_name_type_mismatch():
    with pytest.raises(ValueError, match="does not match"):
        build_runner("codex", RunnerConfig(type="mock"))
