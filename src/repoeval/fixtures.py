from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

import yaml
from pydantic import ValidationError

from repoeval.models import EvalTask, RepoEvalConfig


class FixtureError(ValueError):
    """Raised when RepoEval fixture files are malformed."""


def _plain_model_dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True, exclude_none=True)


def load_config(path: Path) -> RepoEvalConfig:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return RepoEvalConfig.model_validate(payload)
    except FileNotFoundError:
        raise FixtureError(f"Config file not found: {path}") from None
    except (yaml.YAMLError, ValidationError) as exc:
        raise FixtureError(f"Invalid config {path}: {exc}") from exc


def load_tasks(path: Path) -> list[EvalTask]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise FixtureError(f"Tasks file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise FixtureError(f"Invalid tasks YAML {path}: {exc}") from exc

    if not isinstance(payload, dict) or "tasks" not in payload:
        raise FixtureError("Tasks fixture must contain a 'tasks' list")
    if not isinstance(payload["tasks"], list):
        raise FixtureError("Tasks fixture 'tasks' value must be a list")

    try:
        tasks = [EvalTask.model_validate(task) for task in payload["tasks"]]
    except ValidationError as exc:
        raise FixtureError(f"Invalid tasks {path}: {exc}") from exc
    validate_unique_task_ids(tasks)
    return tasks


def write_config(path: Path, config: RepoEvalConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(_plain_model_dump(config), sort_keys=False), encoding="utf-8")


def write_tasks(path: Path, tasks: Sequence[EvalTask]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tasks": [_plain_model_dump(task) for task in tasks]}
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def validate_unique_task_ids(tasks: Sequence[EvalTask]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for task in tasks:
        if task.id in seen:
            duplicates.append(task.id)
        seen.add(task.id)
    if duplicates:
        joined = ", ".join(sorted(set(duplicates)))
        raise FixtureError(f"Duplicate task id(s): {joined}")
