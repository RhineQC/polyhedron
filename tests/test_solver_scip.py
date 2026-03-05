import pytest

from polyhedron.core.model import Model
from polyhedron.modeling.element import Element
from polyhedron.backends.types import SolveStatus

pytestmark = pytest.mark.scip


class Dummy(Element):
    x = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return self.x


def test_solve_scip():
    _ = pytest.importorskip("pyscipopt")
    model = Model("scip")
    element = Dummy(name="e1")
    model.add_element(element)

    @model.constraint(name="c1", foreach=[0])
    def c(_):
        return element.x >= 1

    result = model.solve(time_limit=1)
    assert result.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}

    solved = model.solve(time_limit=1, return_solved_model=True)
    assert solved.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}
    assert solved.metadata.solver_name == "scip"
