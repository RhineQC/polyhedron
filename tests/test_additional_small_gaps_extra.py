from polyhedron.intelligence.branching import BranchingStrategy
from polyhedron.intelligence.context import SolverContext
from polyhedron.intelligence.simple_rounding import SimpleRoundingHeuristic
from polyhedron.intelligence.warm_start import WarmStart
from polyhedron.temporal.time_horizon import TimeHorizon


def test_branching_simple_rounding_and_warm_start_small_gaps() -> None:
    class V:
        def __init__(self, name):
            self.name = name

    vars_ = [V("x_plant"), V("y_other")]
    BranchingStrategy(rule="name", priorities={"plant": 7}).apply(model=None, variables=vars_)
    assert getattr(vars_[0], "_branching_priority") == 7

    class R:
        fractional_vars = vars_

        @staticmethod
        def value(var):
            return 0.8 if "x" in var.name else 0.2

    h = SimpleRoundingHeuristic(threshold=0.5)
    rounded = h.apply(SolverContext(model=object(), current_relaxation=R()))
    assert rounded[vars_[0]] == 1.0
    assert rounded[vars_[1]] == 0.0

    class S:
        def __init__(self):
            self.called = False
            self.solution = None

        def set_warm_start(self, solution, quality):
            self.called = True
            self.solution = (solution, quality)

    sink = S()
    WarmStart(solution={"x": 1.0}, quality=0.9).apply(SolverContext(model=object(), solver=sink))
    assert sink.called
    assert sink.solution == ({"x": 1.0}, 0.9)


def test_time_horizon_string_and_contains() -> None:
    h = TimeHorizon(3, step="1h")
    assert len(h) == 3
    assert list(iter(h)) == [0, 1, 2]
