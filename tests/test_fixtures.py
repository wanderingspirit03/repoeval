import pytest
import yaml

from repoeval.fixtures import (
    load_config,
    load_tasks,
    validate_unique_task_ids,
    write_config,
    write_tasks,
)
from repoeval.models import EvalTask, RepoEvalConfig


def test_write_and_load_default_config(tmp_path):
    path = tmp_path / ".repoeval" / "config.yaml"

    write_config(path, RepoEvalConfig())
    loaded = load_config(path)

    assert loaded.default_verify_commands == ["pytest"]
    assert loaded.runners["mock"].type == "mock"
    raw = yaml.safe_load(path.read_text())
    assert raw["version"] == 1
    assert raw["runners"]["codex"]["args"] == [
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
    ]


def test_load_tasks_validates_yaml_fixture(tmp_path):
    path = tmp_path / "tasks.yaml"
    path.write_text(
        """
tasks:
  - id: fix-1
    name: Fix a bug
    prompt: Make tests pass.
    category: bugfix
    setup_commands:
      - python -m pip install -e .
    verify_commands:
      - pytest
    expected_files:
      - src/repoeval/cli.py
    source:
      type: manual
      changed_files:
        - src/repoeval/cli.py
""".lstrip(),
        encoding="utf-8",
    )

    tasks = load_tasks(path)

    assert len(tasks) == 1
    assert tasks[0].id == "fix-1"
    assert tasks[0].task_type == "bugfix"
    assert tasks[0].source.changed_files == ["src/repoeval/cli.py"]


def test_write_tasks_round_trips_category_alias(tmp_path):
    path = tmp_path / "tasks.yaml"
    task = EvalTask(id="task-1", name="Task", prompt="Do it", task_type="feature")

    write_tasks(path, [task])
    loaded = yaml.safe_load(path.read_text())

    assert loaded["tasks"][0]["category"] == "feature"
    assert load_tasks(path)[0] == task


def test_load_tasks_rejects_duplicate_task_ids(tmp_path):
    path = tmp_path / "tasks.yaml"
    path.write_text(
        """
tasks:
  - id: duplicate
    name: One
    prompt: Do one.
    category: bugfix
  - id: duplicate
    name: Two
    prompt: Do two.
    category: feature
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_tasks(path)


def test_validate_unique_task_ids_rejects_duplicates():
    tasks = [
        EvalTask(id="one", name="One", prompt="Do one.", task_type="bugfix"),
        EvalTask(id="one", name="Two", prompt="Do two.", task_type="feature"),
    ]

    with pytest.raises(ValueError, match="Duplicate task id"):
        validate_unique_task_ids(tasks)
