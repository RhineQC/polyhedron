from polyhedron.intelligence.context import SolverContext
from polyhedron.intelligence.simple_rounding import SimpleRoundingHeuristic
from polyhedron.intelligence.warm_start import WarmStart
from polyhedron.core.variable import Variable, VarType


class DummyRelaxation:
    def __init__(self):
        self.fractional_vars = [Variable(name="x", var_type=VarType.BINARY)]

    def value(self, _var):
        return 0.6


def test_simple_rounding():
    h = SimpleRoundingHeuristic()
    ctx = SolverContext(model=object(), current_relaxation=DummyRelaxation())
    result = h.run(ctx)
    assert result is not None


def test_warm_start_apply():
    class Sink:
        def __init__(self):
            self.values = {}

        def set_warm_start(self, solution, quality=1.0):
            if solution:
                self.values.update(solution)

    x = Variable(name="x", var_type=VarType.BINARY)
    h = WarmStart(solution={x: 1.0})
    ctx = SolverContext(model=object(), solver=Sink())
    h.apply(ctx)
    assert ctx.solver.values[x] == 1.0
