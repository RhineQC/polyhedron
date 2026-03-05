from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Mapping, Optional

from polyhedron.backends.types import SolveStatus
from polyhedron.core.solution import SolvedModel
from polyhedron.core.variable import Variable


@dataclass(frozen=True)
class ModelSnapshot:
    status: SolveStatus
    objective_value: Optional[float]
    kpis: Mapping[str, float] = field(default_factory=dict)
    variable_values: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class DriftThresholds:
    objective_abs: float = 1e-6
    objective_rel: float = 1e-4
    kpi_abs: float = 1e-6
    kpi_rel: float = 1e-4
    allow_status_change: bool = False


@dataclass(frozen=True)
class DriftIssue:
    kind: str
    key: str
    baseline: object
    current: object
    abs_diff: Optional[float] = None
    rel_diff: Optional[float] = None


@dataclass
class RegressionReport:
    issues: list[DriftIssue]

    @property
    def passed(self) -> bool:
        return not self.issues


def _compute_rel_diff(baseline: float, current: float) -> float:
    denom = max(abs(baseline), 1e-12)
    return abs(current - baseline) / denom


def snapshot_solved_model(
    solved: SolvedModel,
    *,
    kpis: Optional[Mapping[str, Callable[[SolvedModel], float]]] = None,
    variables: Optional[Mapping[str, Variable]] = None,
) -> ModelSnapshot:
    kpi_values: Dict[str, float] = {}
    if kpis:
        for name, func in kpis.items():
            kpi_values[name] = float(func(solved))

    variable_values: Dict[str, float] = {}
    if variables:
        for name, var in variables.items():
            variable_values[name] = float(solved.get_value(var))

    return ModelSnapshot(
        status=solved.status,
        objective_value=solved.objective_value,
        kpis=kpi_values,
        variable_values=variable_values,
    )


def compare_snapshots(
    baseline: ModelSnapshot,
    current: ModelSnapshot,
    *,
    thresholds: DriftThresholds = DriftThresholds(),
) -> RegressionReport:
    issues: list[DriftIssue] = []

    if baseline.status != current.status and not thresholds.allow_status_change:
        issues.append(
            DriftIssue(
                kind="status_drift",
                key="status",
                baseline=baseline.status.value,
                current=current.status.value,
            )
        )

    if baseline.objective_value is not None and current.objective_value is not None:
        abs_diff = abs(float(current.objective_value) - float(baseline.objective_value))
        rel_diff = _compute_rel_diff(float(baseline.objective_value), float(current.objective_value))
        if abs_diff > thresholds.objective_abs and rel_diff > thresholds.objective_rel:
            issues.append(
                DriftIssue(
                    kind="objective_drift",
                    key="objective",
                    baseline=baseline.objective_value,
                    current=current.objective_value,
                    abs_diff=abs_diff,
                    rel_diff=rel_diff,
                )
            )

    shared_kpis = set(baseline.kpis) & set(current.kpis)
    for key in sorted(shared_kpis):
        baseline_value = float(baseline.kpis[key])
        current_value = float(current.kpis[key])
        abs_diff = abs(current_value - baseline_value)
        rel_diff = _compute_rel_diff(baseline_value, current_value)
        if abs_diff > thresholds.kpi_abs and rel_diff > thresholds.kpi_rel:
            issues.append(
                DriftIssue(
                    kind="kpi_drift",
                    key=key,
                    baseline=baseline_value,
                    current=current_value,
                    abs_diff=abs_diff,
                    rel_diff=rel_diff,
                )
            )

    return RegressionReport(issues=issues)


def assert_no_regression(report: RegressionReport) -> None:
    if report.passed:
        return
    details = "; ".join(
        f"{issue.kind}:{issue.key} baseline={issue.baseline} current={issue.current}" for issue in report.issues
    )
    raise AssertionError(f"Regression drift detected: {details}")
