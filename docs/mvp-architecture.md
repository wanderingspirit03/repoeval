# RepoEval MVP Architecture and Module Split

## Goal

RepoEval answers one repo-local routing question: which coding agent should handle this repository and task type, based on repeatable fixture tasks, isolated execution, verification commands, scoring records, and generated routing recommendations.

The MVP acceptance target is:

```bash
pip install -e '.[dev]'
repoeval init
repoeval tasks validate
repoeval tasks list
repoeval generate --from-git-history --limit 10
repoeval run --agents mock --tasks .repoeval/tasks.yaml
repoeval report
pytest
ruff check .
```

## Current repository baseline

Current files are intentionally minimal:

- `pyproject.toml`: Hatchling package, `repoeval = "repoeval.cli:app"`, runtime deps `typer`, `pydantic`, `rich`, `pyyaml`, dev deps `pytest`, `ruff`.
- `src/repoeval/cli.py`: Typer app with placeholder `init`, `generate`, `run`, and `report` commands.
- `tests/test_cli.py`: one CLI init smoke test.
- `ci/github-actions-ci.yml`: installs `.[dev]`, runs `ruff check .` and `pytest`.

MVP work should preserve this packaging shape: source lives under `src/repoeval`, tests mirror modules under `tests`, and CLI behavior is exercised with `typer.testing.CliRunner` plus focused unit tests for non-CLI modules.

## Public CLI behavior

All paths are interpreted relative to the current working directory unless explicitly absolute. Commands must return non-zero on validation, runner, setup, verify, or report-generation errors and write human-readable diagnostics to stderr.

### `repoeval init [--path PATH] [--force]`

Creates a repo-local `.repoeval/` directory at `PATH`.

Files created when absent:

- `.repoeval/config.yaml`
- `.repoeval/tasks.yaml`
- `.repoeval/results/` directory
- `.repoeval/runs/` directory for worktrees/temp copies and logs

Default `.repoeval/config.yaml`:

```yaml
version: 1
repo_root: .
results_dir: .repoeval/results
runs_dir: .repoeval/runs
default_verify_commands:
  - pytest
runners:
  mock:
    type: mock
  codex:
    type: codex
    command: codex
    args: [exec, --dangerously-bypass-approvals-and-sandbox]
isolation:
  mode: worktree
  keep_runs: false
report:
  output_dir: .repoeval/results
```

Default `.repoeval/tasks.yaml`:

```yaml
tasks: []
```

`--force` may overwrite starter files; without it, existing files are left unchanged.

### `repoeval tasks validate [--tasks PATH] [--config PATH]`

Loads config and YAML task fixtures, validates all models, verifies unique task IDs, and prints a concise success or error summary. Default task path is `.repoeval/tasks.yaml`; default config path is `.repoeval/config.yaml`.

### `repoeval tasks list [--tasks PATH] [--format table|json]`

Prints task ID, name, category/task type, source, setup command count, verify command count, and expected-file count. `--format json` emits a JSON array matching the loaded task model.

### `repoeval generate --from-git-history --limit N [--output PATH] [--since REF] [--category CATEGORY]`

Generates candidate tasks from local git history. MVP generation is deterministic and offline:

1. Read recent commits with `git log --reverse --name-status` bounded by `--limit` and optional `--since`.
2. Skip merge commits and commits touching only ignored/generated paths.
3. Build one task per selected commit using the commit subject/body, changed paths, and parent SHA in `source` metadata.
4. Write or append generated tasks to `PATH` (default `.repoeval/tasks.yaml`).

Generated tasks are fixtures for future evals, not a production benchmark corpus. They should be understandable and editable YAML.

### `repoeval run --agents AGENTS --tasks PATH [--config PATH] [--output PATH] [--keep-runs]`

Runs every selected task for every requested runner. `AGENTS` is a comma-separated list of runner names from config (`mock`, `codex` for MVP). Default task path is `.repoeval/tasks.yaml`. Default output is `.repoeval/results/results.jsonl`.

For each `(task, runner)` pair:

1. Create isolated checkout/copy.
2. Run task setup commands.
3. Invoke runner with the task prompt and repo path.
4. Run verify commands.
5. Compute diff stats and changed files.
6. Persist a `RunResult` JSON line and a per-run log file.
7. Clean up unless `--keep-runs` or config `isolation.keep_runs` is true.

The command exits non-zero only for harness-level failures (invalid config, invalid tasks, unavailable runner, isolation failure). Individual task verification failures are recorded in result rows and summarized without stopping the whole run.

### `repoeval report [--results PATH] [--output-dir PATH]`

Reads JSONL result records and writes:

- `report.md`: human-readable per-category and per-agent pass rates, runtime, changed-line/diff-size summary, and notable failures.
- `routing.yaml`: deterministic task-category routing recommendations.

MVP routing chooses the highest pass-rate runner per category, then lowest median runtime, then lowest median changed lines, then lexical runner name for stable ties.

## Module and file ownership

Implementation must keep modules narrow so downstream builders can work in parallel without collisions.

### CLI and command wiring

Owner: integration lane.

- `src/repoeval/cli.py`
  - Typer application only: parse options, call service functions, convert exceptions to exit codes.
  - Exports `app` as the console entry point.
  - Adds a `tasks` sub-app for `validate` and `list`.
- `tests/test_cli.py`
  - End-to-end CLI tests with `CliRunner` for command contracts.

Boundary: CLI must not contain core validation, runner, isolation, scoring, or report logic beyond small presentation helpers.

### Config and task models

Owner: models/config lane.

- `src/repoeval/models.py`
  - Pydantic models and enums shared by all modules.
  - Public exports: `RepoEvalConfig`, `RunnerConfig`, `IsolationConfig`, `ReportConfig`, `EvalTask`, `TaskSource`, `RunResult`, `VerifyResult`, `DiffStats`, `RoutingRecommendation`.
- `src/repoeval/fixtures.py`
  - YAML loading/dumping and validation for `.repoeval/config.yaml` and `.repoeval/tasks.yaml`.
  - Public functions: `load_config(path: Path) -> RepoEvalConfig`, `load_tasks(path: Path) -> list[EvalTask]`, `write_config(path: Path, config: RepoEvalConfig) -> None`, `write_tasks(path: Path, tasks: Sequence[EvalTask]) -> None`, `validate_unique_task_ids(tasks: Sequence[EvalTask]) -> None`.
- `tests/test_models.py`
- `tests/test_fixtures.py`

Boundary: no Typer imports, no subprocess execution, no git commands.

### Git-history task generation

Owner: generation lane.

- `src/repoeval/generate.py`
  - Public function: `generate_from_git_history(repo_root: Path, limit: int, since: str | None = None, category: str | None = None) -> list[EvalTask]`.
  - Uses `src/repoeval/git.py` helpers for command execution and parsing.
- `src/repoeval/git.py`
  - Public functions: `run_git(repo_root: Path, args: Sequence[str]) -> str`, `collect_commit_summaries(...) -> list[GitCommitSummary]`, `diff_stats(repo_root: Path, base_ref: str, head_ref: str | None = None) -> DiffStats`.
- `tests/test_generate.py`
- `tests/test_git.py`

Boundary: generation returns model objects; it does not run agents or write reports. CLI or fixtures layer handles writing YAML.

### Isolation

Owner: runner/isolation lane.

- `src/repoeval/isolation.py`
  - Public protocol/class: `IsolatedRepo` with `path: Path`, `log_dir: Path`, `cleanup() -> None`, context-manager support.
  - Public function: `create_isolated_repo(repo_root: Path, runs_dir: Path, task_id: str, runner_name: str, mode: Literal["worktree", "temp-copy"]) -> IsolatedRepo`.
  - Worktree mode uses `git worktree add --detach`; temp-copy mode copies tracked files and excludes `.git`, `.repoeval/results`, `.repoeval/runs`, caches, venvs, and build artifacts.
- `tests/test_isolation.py`

Boundary: isolation creates and removes execution directories only; it does not know task semantics or runner behavior.

### Runner interface: mock and codex

Owner: runner/isolation lane.

- `src/repoeval/runners/base.py`
  - Public protocol: `Runner` with `name: str` and `run(task: EvalTask, repo_path: Path, log_path: Path) -> RunnerResult`.
  - Public model: `RunnerResult` with `exit_code`, `runtime_seconds`, `cost_usd`, `stdout_path`, `stderr_path`, optional `metadata`.
- `src/repoeval/runners/mock.py`
  - Deterministic test runner. MVP behavior: optionally create/update `expected_files`, write a log, and return success unless the prompt or metadata requests a mock failure.
- `src/repoeval/runners/codex.py`
  - Shells out to configured `codex` command with task prompt, working directory, timeout, and log capture.
  - Must not require Codex during unit tests; tests inject fake subprocess calls.
- `src/repoeval/runners/__init__.py`
  - Registry function: `build_runner(name: str, config: RunnerConfig) -> Runner`.
- `tests/test_runners_mock.py`
- `tests/test_runners_codex.py`

Boundary: runners modify only the isolated repo path. They do not run setup/verify commands or write `RunResult` rows.

### Execution, verification, and scoring

Owner: execution/scoring lane.

- `src/repoeval/executor.py`
  - Public function: `run_eval_matrix(config: RepoEvalConfig, tasks: Sequence[EvalTask], runner_names: Sequence[str], output_path: Path, keep_runs: bool = False) -> list[RunResult]`.
  - Orchestrates isolation, setup commands, runner invocation, verify commands, diff stats, result persistence, and cleanup.
- `src/repoeval/commands.py`
  - Public function: `run_command(command: str | Sequence[str], cwd: Path, log_path: Path, timeout_seconds: int | None = None) -> CommandResult`.
- `src/repoeval/scoring.py`
  - Public functions: `build_run_result(...) -> RunResult`, `append_result(path: Path, result: RunResult) -> None`, `load_results(path: Path) -> list[RunResult]`.
- `tests/test_executor.py`
- `tests/test_commands.py`
- `tests/test_scoring.py`

Boundary: executor is the only module that combines config, tasks, isolation, runners, commands, git diff stats, and result writing.

### Report and routing generation

Owner: report/docs lane.

- `src/repoeval/report.py`
  - Public functions: `summarize_results(results: Sequence[RunResult]) -> ReportSummary`, `write_report(summary: ReportSummary, path: Path) -> None`.
- `src/repoeval/routing.py`
  - Public function: `build_routing(results: Sequence[RunResult]) -> list[RoutingRecommendation]`, `write_routing(path: Path, recommendations: Sequence[RoutingRecommendation]) -> None`.
- `tests/test_report.py`
- `tests/test_routing.py`

Boundary: report/routing reads result records only. It does not invoke agents, git, or verification commands.

## Data models

Models use Pydantic v2. YAML serialization should use plain field names and avoid Python-specific tags.

### Config model

```python
class RepoEvalConfig(BaseModel):
    version: Literal[1] = 1
    repo_root: Path = Path(".")
    results_dir: Path = Path(".repoeval/results")
    runs_dir: Path = Path(".repoeval/runs")
    default_setup_commands: list[str] = []
    default_verify_commands: list[str] = ["pytest"]
    runners: dict[str, RunnerConfig]
    isolation: IsolationConfig = IsolationConfig()
    report: ReportConfig = ReportConfig()

class RunnerConfig(BaseModel):
    type: Literal["mock", "codex"]
    command: str | None = None
    args: list[str] = []
    timeout_seconds: int = 900
    env: dict[str, str] = {}

class IsolationConfig(BaseModel):
    mode: Literal["worktree", "temp-copy"] = "worktree"
    keep_runs: bool = False

class ReportConfig(BaseModel):
    output_dir: Path = Path(".repoeval/results")
```

### Task fixture model

`category` and `task_type` are aliases for the same routing dimension. Internally prefer `task_type`; accept `category` in YAML for README compatibility.

```python
class EvalTask(BaseModel):
    id: str
    name: str
    prompt: str
    task_type: str = Field(alias="category")
    setup_commands: list[str] = []
    verify_commands: list[str] = []
    expected_files: list[str] = []
    source: TaskSource | None = None
    metadata: dict[str, Any] = {}

class TaskSource(BaseModel):
    type: Literal["yaml", "git-history", "manual"] = "yaml"
    commit: str | None = None
    parent_commit: str | None = None
    changed_files: list[str] = []
    url: str | None = None
```

Validation requirements:

- `id` is non-empty, stable, unique, and slug-like (`[a-zA-Z0-9_.-]+`).
- `name`, `prompt`, and task type/category are non-empty.
- Command lists contain non-empty strings.
- Expected file paths are relative and cannot traverse above repo root.

### Result and scoring models

```python
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

class CommandResult(BaseModel):
    command: str
    exit_code: int
    runtime_seconds: float
    stdout_path: Path
    stderr_path: Path

class VerifyResult(CommandResult):
    passed: bool

class DiffStats(BaseModel):
    files_touched: list[str] = []
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    changed_lines: int = 0
    insertions: int = 0
    deletions: int = 0

class ExpectedFileResult(BaseModel):
    path: str
    exists: bool

class RoutingRecommendation(BaseModel):
    task_type: str
    recommended_runner: str
    pass_rate: float
    median_runtime_seconds: float
    median_changed_lines: int
    sample_size: int
    alternatives: list[str] = []
```

`status` is `passed` only when the runner exits 0, every setup and verify command exits 0, and every expected file exists. `failed` means the harness ran successfully but task verification failed. `error` means harness setup, isolation, runner availability, timeout, or unexpected exception prevented a normal verification result.

## Test split and quality gates

Unit tests should be fast, deterministic, and avoid real Codex calls.

- `tests/test_cli.py`: CLI command contracts and error codes.
- `tests/test_models.py`: model defaults, alias handling, validation errors.
- `tests/test_fixtures.py`: YAML round-trip, invalid YAML, duplicate IDs.
- `tests/test_generate.py` and `tests/test_git.py`: git-history parsing with temporary git repos or injected command output.
- `tests/test_isolation.py`: worktree/temp-copy creation and cleanup with tiny temp repos.
- `tests/test_runners_mock.py`: deterministic mock behavior.
- `tests/test_runners_codex.py`: command construction and log capture using monkeypatched subprocess; no Codex binary required.
- `tests/test_executor.py`: matrix orchestration using mock runner and temp repos.
- `tests/test_scoring.py`: result status, JSONL append/load, diff-stat mapping.
- `tests/test_report.py`: report markdown content from sample results.
- `tests/test_routing.py`: routing tie-break rules.

Required local gates before merge:

```bash
pip install -e '.[dev]'
ruff check .
pytest
git diff --check
```

Docs-only spec changes may run the already-installed `ruff check .`, `pytest`, and `git diff --check` without reinstalling.

## Parallel implementation boundaries

Recommended downstream work packages:

1. Models/fixtures/init/tasks lane:
   - Owns `models.py`, `fixtures.py`, default YAML templates, `repoeval init`, `repoeval tasks validate/list`, and tests for those files.
   - Must not edit runner/executor/report modules except CLI wiring agreed with integration lane.

2. Generation lane:
   - Owns `git.py`, `generate.py`, `repoeval generate`, and generation tests.
   - Consumes `EvalTask` and fixture writing interfaces; must not change result models without coordination.

3. Runner/executor/scoring lane:
   - Owns `isolation.py`, `commands.py`, `runners/*`, `executor.py`, `scoring.py`, `repoeval run`, and related tests.
   - Consumes models/config/tasks; must not implement reporting beyond producing JSONL records.

4. Report/docs/integration lane:
   - Owns `report.py`, `routing.py`, README quickstart/kill criteria/roadmap updates, `repoeval report`, and final CLI polish.
   - Consumes result records; must not invoke runners.

To reduce merge conflicts, each lane should add its own tests and keep CLI edits additive. If two lanes need `cli.py`, add small command functions only and delegate to service modules.

## Acceptance criteria mapping

- `pip install -e '.[dev]'`: preserved by `pyproject.toml` package layout and CI gates.
- `repoeval init` creates `.repoeval/config.yaml` and `.repoeval/tasks.yaml`: covered by CLI, fixtures, and init tests.
- Task model includes required fields and optional expected files/source metadata: covered by `EvalTask` and `TaskSource`.
- `repoeval tasks validate/list`: covered by fixtures and CLI tasks sub-app.
- `repoeval generate --from-git-history --limit N`: covered by `generate.py`, `git.py`, and CLI command.
- Isolated worktree/temp-copy execution: covered by `isolation.py` and executor tests.
- Mock and Codex runners: covered by `runners/mock.py`, `runners/codex.py`, registry, and tests with Codex mocked.
- Scoring records include verify pass/fail, runtime, diff stats, files touched, changed lines, exit codes, and log path: covered by `RunResult`, `CommandResult`, `VerifyResult`, `DiffStats`, and `scoring.py`.
- `repoeval run --agents mock --tasks .repoeval/tasks.yaml`: covered by executor orchestration and CLI tests.
- `repoeval report` writes `report.md` and `routing.yaml`: covered by report/routing modules and tests.
- README quickstart, example, kill criteria, roadmap: owned by report/docs/integration lane after implementation behavior stabilizes.
- `pytest` and `ruff` pass: required for every lane and CI.

## MVP non-goals

- Hosted service, database, or web UI.
- Real-time dashboards.
- Non-Codex real runners beyond config shape.
- Perfect benchmark generation from arbitrary commits.
- Cross-repository aggregation.
- Accurate cost tracking when a runner cannot emit cost metadata.
