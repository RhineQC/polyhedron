from polyhedron.core.variable import Variable, VarType
from polyhedron.intelligence.branching import BranchingStrategy


def test_branching_priority_applies():
    v = Variable(name="x_commit", var_type=VarType.BINARY)
    strat = BranchingStrategy(rule="most_infeasible", priorities={"commit": 10})
    strat.apply(model=None, variables=[v])
    assert getattr(v, "_branching_priority", None) == 10
