from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Literal

import typer

from repoeval.fixtures import FixtureError, load_config, load_tasks, write_config, write_tasks
from repoeval.generate import generate_from_git_history
from repoeval.isolation import create_isolated_repo
from repoeval.models import (
    CommandResult,
    EvalTask,
    ExpectedFileResult,
    RepoEvalConfig,
    RunnerResult,
    VerifyResult,
)
from repoeval.report import summarize_results, write_report
from repoeval.routing import build_routing, write_routing
from repoeval.runners import build_runner
from repoeval.scoring import append_result, build_run_result, collect_diff_stats, load_results

app = typer.Typer(help="Repo-local eval harness for AI coding agents.")
tasks_app = typer.Typer(help="Validate and inspect RepoEval task fixtures.")
app.add_typer(tasks_app, name="tasks")


@app.command()
def init(
    path: Path = typer.Option(Path("."), help="Repository root"),
    force: bool = typer.Option(False, "--force", help="Overwrite starter files"),
) -> None:
    """Create a starter .repoeval config directory."""
    cfg = path / ".repoeval"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "results").mkdir(exist_ok=True)
    (cfg / "runs").mkdir(exist_ok=True)

    created: list[str] = []
    preserved: list[str] = []
    config_path = cfg / "config.yaml"
    tasks_path = cfg / "tasks.yaml"

    if force or not config_path.exists():
        write_config(config_path, RepoEvalConfig())
        created.append(str(config_path))
    else:
        preserved.append(str(config_path))

    if force or not tasks_path.exists():
        write_tasks(tasks_path, [])
        created.append(str(tasks_path))
    else:
        preserved.append(str(tasks_path))

    typer.echo(f"Initialized {cfg}")
    if created:
        typer.echo("Wrote " + ", ".join(created))
    if preserved:
        typer.echo("left existing " + ", ".join(preserved))


@tasks_app.command("validate")
def tasks_validate(
    tasks: Path = typer.Option(Path(".repoeval/tasks.yaml"), "--tasks", help="Task fixture path"),
    config: Path = typer.Option(Path(".repoeval/config.yaml"), "--config", help="Config path"),
) -> None:
    """Validate task fixtures and config."""
    try:
        if config.exists():
            load_config(config)
        loaded_tasks = load_tasks(tasks)
    except FixtureError as exc:
        typer.echo(f"Invalid tasks: {exc}", err=True)
        raise typer.Exit(1) from exc
    count = len(loaded_tasks)
    suffix = "" if count == 1 else "s"
    typer.echo(f"{count} task{suffix} valid")


@tasks_app.command("list")
def tasks_list(
    tasks: Path = typer.Option(Path(".repoeval/tasks.yaml"), "--tasks", help="Task fixture path"),
    output_format: Literal["table", "json"] = typer.Option(
        "table",
        "--format",
        help="Output format: table or json",
    ),
) -> None:
    """List task fixtures."""
    try:
        loaded_tasks = load_tasks(tasks)
    except FixtureError as exc:
        typer.echo(f"Invalid tasks: {exc}", err=True)
        raise typer.Exit(1) from exc

    if output_format == "json":
        typer.echo(
            json.dumps(
                [
                    task.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for task in loaded_tasks
                ],
                indent=2,
            )
        )
        return

    typer.echo("id\tname\tcategory\tsource\tsetup\tverify\texpected_files")
    for task in loaded_tasks:
        source = task.source.type if task.source else ""
        typer.echo(
            f"{task.id}\t{task.name}\t{task.task_type}\t{source}\t"
            f"{len(task.setup_commands)}\t{len(task.verify_commands)}\t{len(task.expected_files)}"
        )


@app.command()
def generate(
    from_git_history: bool = typer.Option(
        False,
        "--from-git-history",
        help="Generate tasks from recent git commits",
    ),
    limit: int = typer.Option(5, "--limit", min=1, help="Number of tasks to generate"),
    output: Path = typer.Option(Path(".repoeval/tasks.yaml"), "--output", help="Output tasks YAML"),
    since: str | None = typer.Option(None, "--since", help="Only inspect commits after ref"),
    category: str | None = typer.Option(None, "--category", help="Category for generated tasks"),
) -> None:
    """Generate eval tasks."""
    if not from_git_history:
        typer.echo("No generator selected. Use --from-git-history.", err=True)
        raise typer.Exit(1)

    generated_tasks = generate_from_git_history(
        Path.cwd(), limit=limit, since=since, category=category
    )
    existing_tasks: list[EvalTask] = []
    if output.exists():
        try:
            existing_tasks = load_tasks(output)
        except FixtureError as exc:
            typer.echo(f"Invalid existing output tasks: {exc}", err=True)
            raise typer.Exit(1) from exc
    write_tasks(output, [*existing_tasks, *generated_tasks])
    count = len(generated_tasks)
    if count == 0:
        typer.echo("No git history tasks generated; history may be insufficient.")
    else:
        suffix = "" if count == 1 else "s"
        typer.echo(f"Generated {count} task{suffix} into {output}")


def _resolve_repo_path(path: Path, base: Path) -> Path:
    return path if path.is_absolute() else (base / path).resolve()


def _checkout_ref_for_task(task: EvalTask) -> str:
    if task.source and task.source.type == "git-history" and task.source.parent_commit:
        return task.source.parent_commit
    return "HEAD"


def _run_command(command: str, cwd: Path, log_dir: Path, phase: str, index: int) -> CommandResult:
    started = datetime.now(timezone.utc)
    stdout_path = log_dir / f"{phase}-{index}.out"
    stderr_path = log_dir / f"{phase}-{index}.err"
    completed = subprocess.run(
        command,
        cwd=cwd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    runtime_seconds = max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
    return CommandResult(
        command=command,
        exit_code=completed.returncode,
        runtime_seconds=runtime_seconds,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def _run_verify_command(command: str, cwd: Path, log_dir: Path, index: int) -> VerifyResult:
    result = _run_command(command, cwd, log_dir, "verify", index)
    return VerifyResult(**result.model_dump(), passed=result.exit_code == 0)


def _error_runner_result(log_dir: Path, error: str) -> RunnerResult:
    stdout_path = log_dir / "runner.out"
    stderr_path = log_dir / "runner.err"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text(error, encoding="utf-8")
    return RunnerResult(
        exit_code=1,
        runtime_seconds=0.0,
        cost_usd=Decimal("0"),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        metadata={"error": error},
    )


@app.command()
def run(
    agents: str = typer.Option("mock", "--agents", help="Comma-separated runner names"),
    tasks: Path = typer.Option(Path(".repoeval/tasks.yaml"), "--tasks", help="Task fixture path"),
    config: Path = typer.Option(Path(".repoeval/config.yaml"), "--config", help="Config path"),
    results: Path = typer.Option(
        Path(".repoeval/results.jsonl"), "--results", help="Results JSONL path"
    ),
) -> None:
    """Run eval tasks with configured agents and append JSONL results."""
    try:
        cfg = load_config(config) if config.exists() else RepoEvalConfig()
        loaded_tasks = load_tasks(tasks)
    except FixtureError as exc:
        typer.echo(f"Invalid run input: {exc}", err=True)
        raise typer.Exit(1) from exc

    requested_agents = [agent.strip() for agent in agents.split(",") if agent.strip()]
    if not requested_agents:
        typer.echo("No agents selected", err=True)
        raise typer.Exit(1)

    repo_root = _resolve_repo_path(cfg.repo_root, config.parent.parent)
    runs_dir = _resolve_repo_path(cfg.runs_dir, repo_root)
    total = 0

    for task in loaded_tasks:
        for agent_name in requested_agents:
            runner_config = cfg.runners.get(agent_name)
            if runner_config is None:
                typer.echo(f"Unknown agent: {agent_name}", err=True)
                raise typer.Exit(1)
            runner = build_runner(agent_name, runner_config)
            started_at = datetime.now(timezone.utc)
            setup_results: list[CommandResult] = []
            verify_results: list[VerifyResult] = []
            expected_files: list[ExpectedFileResult] = []
            error: str | None = None

            isolated = create_isolated_repo(
                repo_root,
                runs_dir,
                task.id,
                agent_name,
                cfg.isolation.mode,
                checkout_ref=_checkout_ref_for_task(task),
            )
            try:
                commands = [*cfg.default_setup_commands, *task.setup_commands]
                setup_results = [
                    _run_command(command, isolated.path, isolated.log_dir, "setup", idx)
                    for idx, command in enumerate(commands, start=1)
                ]
                runner_result = runner.run(task, isolated.path, isolated.log_dir / "runner.out")
                verify_commands = task.verify_commands or cfg.default_verify_commands
                if agent_name == "mock" and not (isolated.path / "tests").exists():
                    verify_commands = []
                verify_results = [
                    _run_verify_command(command, isolated.path, isolated.log_dir, idx)
                    for idx, command in enumerate(verify_commands, start=1)
                ]
                expected_files = [
                    ExpectedFileResult(
                        path=expected_file, exists=(isolated.path / expected_file).exists()
                    )
                    for expected_file in task.expected_files
                ]
                diff = collect_diff_stats(isolated.path)
            except Exception as exc:  # noqa: BLE001 - record task error and continue writing a result
                error = str(exc)
                runner_result = _error_runner_result(isolated.log_dir, error)
                diff = collect_diff_stats(isolated.path)
            finally:
                ended_at = datetime.now(timezone.utc)
                log_path = isolated.log_dir / "runner.out"
                result = build_run_result(
                    task_id=task.id,
                    task_name=task.name,
                    task_type=task.task_type,
                    runner=agent_name,
                    started_at=started_at,
                    ended_at=ended_at,
                    setup=setup_results,
                    runner_result=runner_result,
                    verify=verify_results,
                    diff=diff,
                    expected_files=expected_files,
                    log_path=log_path,
                    cost_usd=runner_result.cost_usd,
                    error=error,
                )
                append_result(results, result)
                total += 1
                if not cfg.isolation.keep_runs:
                    isolated.cleanup()

    suffix = "" if total == 1 else "s"
    typer.echo(f"Wrote {total} result{suffix} to {results}")


@app.command()
def report(
    results: Path = typer.Option(
        Path(".repoeval/results.jsonl"),
        "--results",
        help="Results JSONL path",
    ),
    output_dir: Path = typer.Option(
        Path(".repoeval"),
        "--output-dir",
        help="Directory for report.md and routing.yaml",
    ),
) -> None:
    """Write report.md and routing.yaml from result records."""
    run_results = load_results(results)
    summary = summarize_results(run_results)
    report_path = output_dir / "report.md"
    routing_path = output_dir / "routing.yaml"
    write_report(summary, report_path)
    write_routing(routing_path, build_routing(run_results))
    typer.echo(f"Wrote {report_path} and {routing_path}")
