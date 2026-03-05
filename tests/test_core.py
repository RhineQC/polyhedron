from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression
from polyhedron.core.variable import Variable, VarType


def test_variable_expression_constraint():
    x = Variable(name="x", var_type=VarType.CONTINUOUS, lower_bound=0, upper_bound=10)
    expr = x + 2
    assert isinstance(expr, Expression)
    cons = expr <= 5
    assert isinstance(cons, Constraint)
    assert cons.sense == "<="
