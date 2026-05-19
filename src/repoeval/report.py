from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Iterable, Sequence

from repoeval.models import RunResult


@dataclass(frozen=True)
class AggregateRow:
    name: str
    runner: str | None
    passed: int
    total: int
    pass_rate: float
    average_runtime_seconds: float
    average_changed_lines: float


@dataclass(frozen=True)
class ReportSummary:
    results: list[RunResult]
    by_runner: list[AggregateRow]
    by_task_type: list[AggregateRow]
    failures: list[RunResult]


def _aggregate(results: Iterable[RunResult], *, include_runner: bool) -> list[AggregateRow]:
    buckets: dict[tuple[str, str | None], list[RunResult]] = {}
    for result in results:
        key = (result.task_type if include_runner else result.runner, result.runner if include_runner else None)
        buckets.setdefault(key, []).append(result)

    rows: list[AggregateRow] = []
    for (name, runner), bucket in buckets.items():
        total = len(bucket)
        passed = sum(result.status == "passed" for result in bucket)
        rows.append(
            AggregateRow(
                name=name,
                runner=runner,
                passed=passed,
                total=total,
                pass_rate=passed / total if total else 0.0,
                average_runtime_seconds=mean(result.runtime_seconds for result in bucket),
                average_changed_lines=mean(result.diff.changed_lines for result in bucket),
            )
        )
    return sorted(rows, key=lambda row: (row.name, row.runner or ""))


def summarize_results(results: Sequence[RunResult]) -> ReportSummary:
    result_list = list(results)
    return ReportSummary(
        results=result_list,
        by_runner=_aggregate(result_list, include_runner=False),
        by_task_type=_aggregate(result_list, include_runner=True),
        failures=[result for result in result_list if result.status != "passed"],
    )


def _rate(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_report(summary: ReportSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RepoEval Report",
        "",
        f"Total runs: {len(summary.results)}",
        "",
        "## By Runner",
        "",
        "| Runner | Passed | Pass Rate | Avg Runtime (s) | Avg Changed Lines |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary.by_runner:
        lines.append(
            f"| {row.name} | {row.passed}/{row.total} | {_rate(row.pass_rate)} | "
            f"{row.average_runtime_seconds:.2f} | {row.average_changed_lines:.1f} |"
        )

    lines.extend(
        [
            "",
            "## By Task Type",
            "",
            "| Task Type | Runner | Passed | Pass Rate | Avg Runtime (s) | Avg Changed Lines |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary.by_task_type:
        lines.append(
            f"| {row.name} | {row.runner} | {row.passed}/{row.total} | {_rate(row.pass_rate)} | "
            f"{row.average_runtime_seconds:.2f} | {row.average_changed_lines:.1f} |"
        )

    lines.extend(["", "## Notable Failures", ""])
    if not summary.failures:
        lines.append("No failures recorded.")
    else:
        for result in summary.failures:
            lines.append(
                f"- {result.task_id} ({result.task_type}, {result.runner}) status={result.status} "
                f"log={result.log_path}"
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
