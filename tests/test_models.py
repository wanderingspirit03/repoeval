from pathlib import Path

import pytest
from pydantic import ValidationError

from repoeval.models import EvalTask, RepoEvalConfig, TaskSource


def test_config_defaults_match_init_contract():
    config = RepoEvalConfig()

    assert config.version == 1
    assert config.repo_root == Path(".")
    assert config.results_dir == Path(".repoeval/results")
    assert config.runs_dir == Path(".repoeval/runs")
    assert config.default_verify_commands == ["pytest"]
    assert config.runners["mock"].type == "mock"
    assert config.runners["codex"].command == "codex"
    assert config.isolation.mode == "worktree"


def test_eval_task_accepts_category_alias_and_source_metadata():
    task = EvalTask.model_validate(
        {
            "id": "fix-bug_1",
            "name": "Fix bug",
            "prompt": "Fix the failing test.",
            "category": "bugfix",
            "setup_commands": ["python -m pip install -e ."],
            "verify_commands": ["pytest tests/test_bug.py"],
            "expected_files": ["src/repoeval/bug.py"],
            "source": {
                "type": "git-history",
                "commit": "abc123",
                "parent_commit": "def456",
                "changed_files": ["src/repoeval/bug.py"],
            },
        }
    )

    assert task.task_type == "bugfix"
    assert task.source == TaskSource(
        type="git-history",
        commit="abc123",
        parent_commit="def456",
        changed_files=["src/repoeval/bug.py"],
    )
    assert task.model_dump(by_alias=True)["category"] == "bugfix"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "not a slug!"),
        ("name", ""),
        ("prompt", "   "),
        ("category", ""),
        ("setup_commands", [""]),
        ("verify_commands", ["   "]),
        ("expected_files", ["../secret.txt"]),
        ("expected_files", ["/tmp/secret.txt"]),
    ],
)
def test_eval_task_rejects_invalid_required_fields(field, value):
    payload = {
        "id": "valid-id",
        "name": "Valid task",
        "prompt": "Do the work.",
        "category": "bugfix",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        EvalTask.model_validate(payload)
