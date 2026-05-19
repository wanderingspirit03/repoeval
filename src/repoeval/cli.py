from __future__ import annotations

from pathlib import Path
import typer

app = typer.Typer(help="Repo-local eval harness for AI coding agents.")


@app.command()
def init(path: Path = typer.Option(Path("."), help="Repository root")) -> None:
    """Create a starter .repoeval config directory."""
    cfg = path / ".repoeval"
    cfg.mkdir(parents=True, exist_ok=True)
    tasks = cfg / "tasks.yaml"
    if not tasks.exists():
        tasks.write_text("tasks: []
", encoding="utf-8")
    typer.echo(f"Initialized {cfg}")


@app.command()
def generate(limit: int = typer.Option(5, min=1, help="Number of tasks to generate")) -> None:
    """Placeholder for generating eval tasks from git history."""
    typer.echo(f"TODO: generate {limit} tasks from git history")


@app.command()
def run(agents: str = typer.Option("mock", help="Comma-separated runner names")) -> None:
    """Placeholder for running eval tasks."""
    typer.echo(f"TODO: run evals with agents: {agents}")


@app.command()
def report() -> None:
    """Placeholder for emitting report artifacts."""
    typer.echo("TODO: write report.md, results.jsonl, routing.yaml")
