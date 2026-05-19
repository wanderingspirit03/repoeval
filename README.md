# RepoEval

RepoEval is an open-source CLI for answering one practical question:

> Which AI coding agent/model should I use for **this repo** and **this task type**?

It creates repo-local eval tasks, runs competing agents in isolated git worktrees, scores outputs with tests/lint/cost/latency/diff metrics, and emits a routing recommendation.

## Target MVP

```bash
repoeval init
repoeval generate --from-git-history --limit 10
repoeval run --agents claude-code,codex,gemini-flash
repoeval report
```

## MVP acceptance criteria

- Generates at least 5 eval tasks from git history or explicit YAML fixtures.
- Runs each task in isolated git worktrees with clean setup/teardown.
- Supports at least one real runner (`codex exec`) and one deterministic mock runner for tests.
- Scores pass/fail via configured commands, runtime, diff size, files touched, and optional cost metadata.
- Produces `report.md`, `results.jsonl`, and `routing.yaml`.
- Has a test suite covering core planning/scoring/reporting behavior.

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```
