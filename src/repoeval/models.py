from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


_SLUG_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


class RunnerConfig(BaseModel):
    type: Literal["mock", "codex"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    timeout_seconds: int = 900
    env: dict[str, str] = Field(default_factory=dict)


class IsolationConfig(BaseModel):
    mode: Literal["worktree", "temp-copy"] = "worktree"
    keep_runs: bool = False


class ReportConfig(BaseModel):
    output_dir: Path = Path(".repoeval/results")


class RepoEvalConfig(BaseModel):
    version: Literal[1] = 1
    repo_root: Path = Path(".")
    results_dir: Path = Path(".repoeval/results")
    runs_dir: Path = Path(".repoeval/runs")
    default_setup_commands: list[str] = Field(default_factory=list)
    default_verify_commands: list[str] = Field(default_factory=lambda: ["pytest"])
    runners: dict[str, RunnerConfig] = Field(
        default_factory=lambda: {
            "mock": RunnerConfig(type="mock"),
            "codex": RunnerConfig(
                type="codex",
                command="codex",
                args=["exec", "--dangerously-bypass-approvals-and-sandbox"],
            ),
        }
    )
    isolation: IsolationConfig = Field(default_factory=IsolationConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)


class TaskSource(BaseModel):
    type: Literal["yaml", "git-history", "manual"] = "yaml"
    commit: str | None = None
    parent_commit: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    target_file_hashes: dict[str, str] = Field(default_factory=dict)
    url: str | None = None


class EvalTask(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    prompt: str
    task_type: str = Field(alias="category")
    setup_commands: list[str] = Field(default_factory=list)
    verify_commands: list[str] = Field(default_factory=list)
    expected_files: list[str] = Field(default_factory=list)
    source: TaskSource | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value or not _SLUG_RE.fullmatch(value):
            raise ValueError("task id must be non-empty and slug-like")
        return value

    @field_validator("name", "prompt", "task_type")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must be non-empty")
        return value

    @field_validator("setup_commands", "verify_commands")
    @classmethod
    def validate_commands(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("commands must be non-empty")
        return values

    @field_validator("expected_files")
    @classmethod
    def validate_expected_files(cls, values: list[str]) -> list[str]:
        for value in values:
            path = Path(value)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("expected files must be relative and stay within repo root")
        return values


class CommandResult(BaseModel):
    command: str
    exit_code: int
    runtime_seconds: float
    stdout_path: Path
    stderr_path: Path


class VerifyResult(CommandResult):
    passed: bool


class RunnerResult(BaseModel):
    exit_code: int
    runtime_seconds: float
    cost_usd: Decimal | None = None
    stdout_path: Path
    stderr_path: Path
    metadata: dict[str, Any] = Field(default_factory=dict)


class DiffStats(BaseModel):
    files_touched: list[str] = Field(default_factory=list)
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    changed_lines: int = 0
    insertions: int = 0
    deletions: int = 0


class ExpectedFileResult(BaseModel):
    path: str
    exists: bool


class RunResult(BaseModel):
    schema_version: Literal[1] = 1
    task_id: str
    task_name: str
    task_type: str
    runner: str
    status: Literal["passed", "failed", "error"]
    started_at: datetime
    ended_at: datetime
    runtime_seconds: float
    setup: list[CommandResult]
    runner_result: RunnerResult
    verify: list[VerifyResult]
    diff: DiffStats
    expected_files: list[ExpectedFileResult]
    log_path: Path
    cost_usd: Decimal | None = None
    error: str | None = None


class RoutingRecommendation(BaseModel):
    task_type: str
    recommended_runner: str
    pass_rate: float
    median_runtime_seconds: float
    median_changed_lines: int
    sample_size: int
    alternatives: list[str] = Field(default_factory=list)
