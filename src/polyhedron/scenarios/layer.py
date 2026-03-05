from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable, Iterable, List, Optional

from polyhedron.backends.types import SolveStatus


@dataclass(frozen=True)
class ScenarioCase:
    name: str
    mutate: Optional[Callable[[object], None]] = None
    description: str = ""


@dataclass(frozen=True)
class ScenarioRunResult:
    name: str
    status: SolveStatus
    objective_value: Optional[float]
    solve_time: float
    error: Optional[str] = None


@dataclass
class ScenarioBatchReport:
    results: List[ScenarioRunResult] = field(default_factory=list)

    def best_feasible(self) -> Optional[ScenarioRunResult]:
        feasible = [
            result
            for result in self.results
            if result.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE} and result.objective_value is not None
        ]
        if not feasible:
            return None
        return min(feasible, key=lambda item: float(item.objective_value))

    def worst_feasible(self) -> Optional[ScenarioRunResult]:
        feasible = [
            result
            for result in self.results
            if result.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE} and result.objective_value is not None
        ]
        if not feasible:
            return None
        return max(feasible, key=lambda item: float(item.objective_value))

    def to_markdown(self) -> str:
        lines = ["## Scenario Batch Report", "", "| Scenario | Status | Objective | Solve Time (s) |", "|---|---|---:|---:|"]
        for result in self.results:
            objective = "-" if result.objective_value is None else f"{result.objective_value:.6g}"
            lines.append(f"| {result.name} | {result.status.value} | {objective} | {result.solve_time:.3f} |")
        return "\n".join(lines)


class ScenarioRunner:
    def __init__(self, model_factory: Callable[[], object]):
        self.model_factory = model_factory

    def run(
        self,
        cases: Iterable[ScenarioCase],
        *,
        time_limit: Optional[float] = None,
        mip_gap: float = 0.01,
    ) -> ScenarioBatchReport:
        report = ScenarioBatchReport()

        for case in cases:
            model = self.model_factory()
            if case.mutate is not None:
                case.mutate(model)

            start = perf_counter()
            try:
                solved = model.solve(time_limit=time_limit, mip_gap=mip_gap, return_solved_model=True)
                elapsed = perf_counter() - start
                report.results.append(
                    ScenarioRunResult(
                        name=case.name,
                        status=solved.status,
                        objective_value=solved.objective_value,
                        solve_time=elapsed,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                elapsed = perf_counter() - start
                report.results.append(
                    ScenarioRunResult(
                        name=case.name,
                        status=SolveStatus.ERROR,
                        objective_value=None,
                        solve_time=elapsed,
                        error=str(exc),
                    )
                )

        return report


def base_best_worst_cases(
    *,
    best_case: Callable[[object], None],
    worst_case: Callable[[object], None],
) -> List[ScenarioCase]:
    return [
        ScenarioCase(name="base"),
        ScenarioCase(name="best", mutate=best_case),
        ScenarioCase(name="worst", mutate=worst_case),
    ]
