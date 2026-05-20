from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml
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
    rec = json.loads(results_path.read_text(encoding="utf-8"))
    assert rec["status"] == "passed"
    assert rec["diff"]["files_touched"] == ["src/example.py"]

    report_result = runner.invoke(app, ["report"])
    assert report_result.exit_code == 0, report_result.output
    assert (tmp_path / ".repoeval" / "report.md").exists()
    assert (tmp_path / ".repoeval" / "routing.yaml").exists()


def test_git_history_modified_file_requires_recreating_target_content(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    assert_modified_git_history_stale_content_fails(tmp_path, monkeypatch, isolation_mode="worktree")


def test_git_history_modified_file_requires_recreating_target_content_in_temp_copy(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    assert_modified_git_history_stale_content_fails(tmp_path, monkeypatch, isolation_mode="temp-copy")


def assert_modified_git_history_stale_content_fails(
    tmp_path: Path, monkeypatch, *, isolation_mode: str
) -> None:  # noqa: ANN001
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "repoeval@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "RepoEval Test"], cwd=tmp_path, check=True)
    commit_file(tmp_path, "src/example.py", "def value():\n    return 1\n", "Initial implementation")
    commit_file(
        tmp_path,
        "src/example.py",
        "def value():\n    return 1\n\n\ndef added():\n    return 2\n",
        "Add helper",
    )

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    init_result = runner.invoke(app, ["init", "--force"])
    assert init_result.exit_code == 0, init_result.output
    config_path = tmp_path / ".repoeval" / "config.yaml"
    config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config_payload["isolation"]["mode"] = isolation_mode
    config_path.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")
    generate_result = runner.invoke(app, ["generate", "--from-git-history", "--limit", "1"])
    assert generate_result.exit_code == 0, generate_result.output

    task = yaml.safe_load((tmp_path / ".repoeval" / "tasks.yaml").read_text(encoding="utf-8"))["tasks"][0]
    assert task["source"]["changed_files"] == ["src/example.py"]

    results_path = tmp_path / ".repoeval" / "results.jsonl"
    results_path.write_text("", encoding="utf-8")
    run_result = runner.invoke(app, ["run", "--agents", "mock", "--tasks", ".repoeval/tasks.yaml"])
    assert run_result.exit_code == 0, run_result.output

    rec = json.loads(results_path.read_text(encoding="utf-8"))
    assert rec["status"] == "failed"
    assert rec["verify"][-1]["command"].startswith("git-history target content matches")
    assert rec["verify"][-1]["passed"] is False
    assert rec["diff"]["files_touched"] == []
    assert rec["diff"]["changed_lines"] == 0
    assert rec["expected_files"] == [{"path": "src/example.py", "exists": True}]
