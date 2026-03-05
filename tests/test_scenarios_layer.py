from dataclasses import dataclass

from polyhedron.backends.types import SolveStatus
from polyhedron.scenarios import ScenarioCase, ScenarioRunner


@dataclass
class FakeSolved:
    status: SolveStatus
    objective_value: float


class FakeModel:
    def __init__(self) -> None:
        self.score = 1.0

    def solve(self, **_kwargs):
        return FakeSolved(status=SolveStatus.OPTIMAL, objective_value=self.score)


def test_scenario_runner_batch_and_best_worst() -> None:
    runner = ScenarioRunner(model_factory=FakeModel)

    def best_case(model: FakeModel) -> None:
        model.score = 0.5

    def worst_case(model: FakeModel) -> None:
        model.score = 3.0

    report = runner.run(
        [
            ScenarioCase("base"),
            ScenarioCase("best", mutate=best_case),
            ScenarioCase("worst", mutate=worst_case),
        ]
    )

    assert len(report.results) == 3
    assert report.best_feasible() is not None
    assert report.best_feasible().name == "best"
    assert report.worst_feasible() is not None
    assert report.worst_feasible().name == "worst"
