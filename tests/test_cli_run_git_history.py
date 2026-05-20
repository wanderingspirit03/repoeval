from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml
from typer.testing import CliRunner

from repoeval.cli import app


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _commit_file(repo: Path, relative: str, content: str, message: str) -> str:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", relative)
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _make_repo_with_history(repo: Path) -> tuple[str, str]:
    _git(repo, "init")
    _git(repo, "config", "user.email", "repoeval@example.invalid")
    _git(repo, "config", "user.name", "RepoEval Test")
    parent = _commit_file(repo, "README.md", "# Example\n", "Initial docs")
    target = _commit_file(repo, "src/example.py", "print('hello')\n", "Add example implementation")
    return parent, target


def test_run_git_history_task_starts_from_parent_commit_and_records_mock_diff(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    parent, target = _make_repo_with_history(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0, init_result.output
    generate_result = runner.invoke(app, ["generate", "--from-git-history", "--limit", "1"])
    assert generate_result.exit_code == 0, generate_result.output

    task_payload = yaml.safe_load(
        (tmp_path / ".repoeval" / "tasks.yaml").read_text(encoding="utf-8")
    )
    task = task_payload["tasks"][0]
    assert task["source"]["commit"] == target
    assert task["source"]["parent_commit"] == parent
    assert (
        "src/example.py" not in _git(tmp_path, "ls-tree", "-r", "--name-only", parent).splitlines()
    )

    results_path = tmp_path / ".repoeval" / "results.jsonl"
    run_result = runner.invoke(app, ["run", "--agents", "mock", "--tasks", ".repoeval/tasks.yaml"])

    assert run_result.exit_code == 0, run_result.output
    result = json.loads(results_path.read_text(encoding="utf-8").strip())
    assert result["status"] == "passed"
    assert result["expected_files"] == [{"path": "src/example.py", "exists": True}]
    assert result["diff"]["files_touched"] == ["src/example.py"]
    assert result["diff"]["files_added"] == 1
    assert result["diff"]["changed_lines"] > 0


def test_run_git_history_without_parent_commit_keeps_head_semantics(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    _make_repo_with_history(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0, init_result.output
    tasks_path = tmp_path / ".repoeval" / "tasks.yaml"
    tasks_path.write_text(
        yaml.safe_dump(
            {
                "tasks": [
                    {
                        "id": "manual-history-no-parent",
                        "name": "No parent history task",
                        "prompt": "Touch expected file if missing.",
                        "category": "git-history",
                        "verify_commands": [],
                        "expected_files": ["src/example.py"],
                        "source": {
                            "type": "git-history",
                            "commit": _git(tmp_path, "rev-parse", "HEAD"),
                            "changed_files": ["src/example.py"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    results_path = tmp_path / ".repoeval" / "results.jsonl"
    run_result = runner.invoke(app, ["run", "--agents", "mock", "--tasks", str(tasks_path)])

    assert run_result.exit_code == 0, run_result.output
    result = json.loads(results_path.read_text(encoding="utf-8").strip())
    assert result["status"] == "passed"
    assert result["expected_files"] == [{"path": "src/example.py", "exists": True}]
    assert result["diff"]["changed_lines"] == 0


def test_run_manual_task_preserves_existing_head_behavior(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    _make_repo_with_history(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    init_result = runner.invoke(app, ["init"])
    assert init_result.exit_code == 0, init_result.output
    tasks_path = tmp_path / ".repoeval" / "tasks.yaml"
    tasks_path.write_text(
        yaml.safe_dump(
            {
                "tasks": [
                    {
                        "id": "manual-task",
                        "name": "Manual task",
                        "prompt": "Touch expected file if missing.",
                        "category": "manual",
                        "verify_commands": [],
                        "expected_files": ["src/example.py"],
                        "source": {"type": "manual", "changed_files": ["src/example.py"]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    results_path = tmp_path / ".repoeval" / "results.jsonl"
    run_result = runner.invoke(app, ["run", "--agents", "mock", "--tasks", str(tasks_path)])

    assert run_result.exit_code == 0, run_result.output
    result = json.loads(results_path.read_text(encoding="utf-8").strip())
    assert result["status"] == "passed"
    assert result["expected_files"] == [{"path": "src/example.py", "exists": True}]
    assert result["diff"]["changed_lines"] == 0
