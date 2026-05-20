import subprocess

import pytest

from repoeval.generate import generate_from_git_history
from repoeval.git import collect_commit_summaries


def run(command, cwd):
    subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)


def commit_file(repo, relative_path, content, message):
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    run(["git", "add", str(relative_path)], cwd=repo)
    run(["git", "commit", "-m", message], cwd=repo)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


@pytest.fixture
def git_repo(tmp_path):
    run(["git", "init"], cwd=tmp_path)
    run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)
    run(["git", "config", "user.name", "Test User"], cwd=tmp_path)
    return tmp_path


def test_collect_commit_summaries_reads_recent_commits_with_changed_files(git_repo):
    first = commit_file(git_repo, "README.md", "hello", "Initial docs")
    second = commit_file(git_repo, "src/app.py", "print('hi')\n", "Add app")

    commits = collect_commit_summaries(git_repo, limit=2)

    assert [commit.subject for commit in commits] == ["Initial docs", "Add app"]
    assert [commit.commit for commit in commits] == [first, second]
    assert commits[0].parent_commit is None
    assert commits[1].parent_commit == first
    assert commits[1].changed_files == ["src/app.py"]


def test_generate_from_git_history_builds_deterministic_eval_tasks(git_repo):
    commit_file(git_repo, "README.md", "hello", "Initial docs")
    second = commit_file(git_repo, "src/app.py", "print('hi')\n", "Add app")

    tasks = generate_from_git_history(git_repo, limit=1, category="feature")

    assert len(tasks) == 1
    task = tasks[0]
    assert task.id.startswith("git-add-app-")
    assert task.name == "Add app"
    assert "Add app" in task.prompt
    assert "src/app.py" in task.prompt
    assert task.task_type == "feature"
    assert task.verify_commands == ["pytest"]
    assert task.expected_files == ["src/app.py"]
    assert task.source.type == "git-history"
    assert task.source.commit == second
    assert task.source.parent_commit is not None
    assert task.source.changed_files == ["src/app.py"]


def test_generate_from_git_history_gracefully_handles_no_commits(tmp_path):
    run(["git", "init"], cwd=tmp_path)

    tasks = generate_from_git_history(tmp_path, limit=10)

    assert tasks == []
