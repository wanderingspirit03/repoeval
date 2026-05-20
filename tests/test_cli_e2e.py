from __future__ import annotations

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from repoeval.cli import app


def commit_file(repo: Path, relative: str, content: str, message: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", relative], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True)


def test_mock_runner_workflow_end_to_end(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "repoeval@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "RepoEval Test"], cwd=tmp_path, check=True)
    commit_file(tmp_path, "README.md", "# Example\n", "Initial docs")
    commit_file(tmp_path, "src/example.py", "print('hello')\n", "Add example implementation")

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0, init_result.output
    assert (tmp_path / ".repoeval" / "config.yaml").exists()
    assert (tmp_path / ".repoeval" / "tasks.yaml").exists()

    generate_result = runner.invoke(app, ["generate", "--from-git-history", "--limit", "1"])
    assert generate_result.exit_code == 0, generate_result.output
    assert "Generated 1 task" in generate_result.output

    validate_result = runner.invoke(app, ["tasks", "validate"])
    assert validate_result.exit_code == 0, validate_result.output
    assert "1 task valid" in validate_result.output

    list_result = runner.invoke(app, ["tasks", "list"])
    assert list_result.exit_code == 0, list_result.output
    assert "id\tname\tcategory" in list_result.output

    run_result = runner.invoke(
        app,
        ["run", "--agents", "mock", "--tasks", ".repoeval/tasks.yaml"],
    )
    assert run_result.exit_code == 0, run_result.output
    results_path = tmp_path / ".repoeval" / "results.jsonl"
    assert results_path.exists()
    assert results_path.read_text(encoding="utf-8").count("\n") == 1

    report_result = runner.invoke(app, ["report"])
    assert report_result.exit_code == 0, report_result.output
    assert (tmp_path / ".repoeval" / "report.md").exists()
    assert (tmp_path / ".repoeval" / "routing.yaml").exists()
