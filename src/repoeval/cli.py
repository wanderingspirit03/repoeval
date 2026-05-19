from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import typer

from repoeval.fixtures import FixtureError, load_config, load_tasks, write_config, write_tasks
from repoeval.generate import generate_from_git_history
from repoeval.models import EvalTask, RepoEvalConfig
from repoeval.report import summarize_results, write_report
from repoeval.routing import build_routing, write_routing
from repoeval.scoring import load_results

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
                [task.model_dump(mode="json", by_alias=True, exclude_none=True) for task in loaded_tasks],
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

    generated_tasks = generate_from_git_history(Path.cwd(), limit=limit, since=since, category=category)
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


@app.command()
def run(agents: str = typer.Option("mock", help="Comma-separated runner names")) -> None:
    """Placeholder for running eval tasks."""
    typer.echo(f"TODO: run evals with agents: {agents}")


@app.command()
def report(
    results: Path = typer.Option(
        Path(".repoeval/results/results.jsonl"),
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
