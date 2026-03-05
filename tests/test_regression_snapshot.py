import pytest

from polyhedron.backends.types import SolveStatus
from polyhedron.regression import (
    DriftThresholds,
    ModelSnapshot,
    assert_no_regression,
    compare_snapshots,
)


def test_regression_detects_objective_drift() -> None:
    baseline = ModelSnapshot(status=SolveStatus.OPTIMAL, objective_value=100.0, kpis={"cost": 100.0})
    current = ModelSnapshot(status=SolveStatus.OPTIMAL, objective_value=120.0, kpis={"cost": 120.0})

    report = compare_snapshots(
        baseline,
        current,
        thresholds=DriftThresholds(objective_abs=1.0, objective_rel=0.01, kpi_abs=1.0, kpi_rel=0.01),
    )
    assert not report.passed
    assert any(issue.kind == "objective_drift" for issue in report.issues)

    with pytest.raises(AssertionError):
        assert_no_regression(report)
