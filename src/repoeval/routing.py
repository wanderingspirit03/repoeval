from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Sequence

import yaml

from repoeval.models import RoutingRecommendation, RunResult


def build_routing(results: Sequence[RunResult]) -> list[RoutingRecommendation]:
    by_task_type_runner: dict[tuple[str, str], list[RunResult]] = {}
    for result in results:
        by_task_type_runner.setdefault((result.task_type, result.runner), []).append(result)

    by_task_type: dict[str, list[RoutingRecommendation]] = {}
    for (task_type, runner), bucket in by_task_type_runner.items():
        total = len(bucket)
        passed = sum(result.status == "passed" for result in bucket)
        recommendation = RoutingRecommendation(
            task_type=task_type,
            recommended_runner=runner,
            pass_rate=passed / total if total else 0.0,
            median_runtime_seconds=float(median(result.runtime_seconds for result in bucket)),
            median_changed_lines=int(median(result.diff.changed_lines for result in bucket)),
            sample_size=total,
        )
        by_task_type.setdefault(task_type, []).append(recommendation)

    recommendations: list[RoutingRecommendation] = []
    for task_type, candidates in sorted(by_task_type.items()):
        ranked = sorted(
            candidates,
            key=lambda item: (
                -item.pass_rate,
                item.median_runtime_seconds,
                item.median_changed_lines,
                item.recommended_runner,
            ),
        )
        winner = ranked[0].model_copy(
            update={"alternatives": [item.recommended_runner for item in ranked[1:]]}
        )
        recommendations.append(winner)
    return recommendations


def write_routing(path: Path, recommendations: Sequence[RoutingRecommendation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "routes": {
            item.task_type: {
                "recommended_runner": item.recommended_runner,
                "pass_rate": item.pass_rate,
                "median_runtime_seconds": item.median_runtime_seconds,
                "median_changed_lines": item.median_changed_lines,
                "sample_size": item.sample_size,
                "alternatives": item.alternatives,
            }
            for item in recommendations
        },
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
