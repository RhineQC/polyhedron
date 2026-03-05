import math

import pytest

from polyhedron.backends.types import SolveResult, SolveStatus
from polyhedron.core.model import Model
from polyhedron.core.solution import Solution, SolveMetadata, SolvedModel
from polyhedron.modeling.element import Element


class Dummy(Element):
    x = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return self.x


def test_solution_is_immutable_and_copies_values():
    model = Model("m")
    element = Dummy("e1")
    model.add_element(element)

    values = {element.x: 2.0}
    solution = Solution(
        status=SolveStatus.OPTIMAL,
        objective_value=2.0,
        values=values,
        solver_name="test",
    )

    values[element.x] = 3.0
    assert solution.values[element.x] == 2.0

    with pytest.raises(TypeError):
        solution.values[element.x] = 4.0  # type: ignore[misc]


def test_solution_rejects_nan_and_inf():
    model = Model("m")
    element = Dummy("e1")
    model.add_element(element)

    with pytest.raises(ValueError):
        Solution(
            status=SolveStatus.OPTIMAL,
            objective_value=1.0,
            values={element.x: math.nan},
            solver_name="test",
        )

    with pytest.raises(ValueError):
        Solution(
            status=SolveStatus.OPTIMAL,
            objective_value=math.inf,
            values={element.x: 1.0},
            solver_name="test",
        )


def test_solved_model_value_access_and_transfer():
    model_a = Model("a")
    element_a = Dummy("e1")
    model_a.add_element(element_a)

    solution = Solution(
        status=SolveStatus.OPTIMAL,
        objective_value=5.0,
        values={element_a.x: 5.0},
        solver_name="test",
    )
    metadata = SolveMetadata(solver_name="test", time_limit=None, mip_gap=0.01)
    solved = SolvedModel(model=model_a, solution=solution, metadata=metadata)

    assert solved.get_value(element_a.x) == 5.0
    assert solved.get_values([element_a.x])[element_a.x] == 5.0

    model_b = Model("b")
    element_b = Dummy("e1")
    model_b.add_element(element_b)

    transferred = solved.with_values(model_b)
    assert transferred.get_value(element_b.x) == 5.0


def test_solution_from_solve_result():
    model = Model("m")
    element = Dummy("e1")
    model.add_element(element)

    result = SolveResult(
        status=SolveStatus.FEASIBLE,
        objective_value=3.0,
        values={element.x: 3.0},
        solver_name="test",
    )
    solution = Solution.from_solve_result(result)
    assert solution.status == SolveStatus.FEASIBLE
    assert solution.values[element.x] == 3.0
