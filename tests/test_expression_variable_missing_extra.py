import builtins

import pytest

from polyhedron.core.expression import Expression
from polyhedron.core.scenario import ScenarioValues
from polyhedron.core.variable import VarType, Variable


def test_expression_rsub_and_quadratic_methods() -> None:
    x = Variable("x", VarType.CONTINUOUS, 0, 10)
    y = Variable("y", VarType.CONTINUOUS, 0, 10)
    s = ScenarioValues({"a": 1.0})

    expr = Expression([(x, 1.0)], constant=2.0, scenario_terms=[(s, 1.0)])

    out = y - expr
    assert isinstance(out, Expression)

    out2 = s - expr
    assert isinstance(out2, Expression)

    unchanged = Expression([(x, 1.0)]).resolve_scenario("a")
    assert isinstance(unchanged, Expression)

    q = x * y
    assert (q * 2).coefficient == 2.0
    assert (2 * q).coefficient == 2.0
    assert (q <= 1).sense == "<="
    assert (q >= 1).sense == ">="
    assert (q == 1).sense == "=="


def test_expression_internal_import_failure_branches(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "polyhedron.core.variable":
            raise ImportError("blocked var")
        if name == "polyhedron.core.scenario":
            raise ImportError("blocked scenario")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    # _is_variable and _is_scenario_values fallback False on import errors.
    assert Expression._is_variable(object()) is False
    assert Expression._is_scenario_values(object()) is False


def test_variable_remaining_branches() -> None:
    x = Variable("x", VarType.CONTINUOUS, 0, 10)
    y = Variable("y", VarType.CONTINUOUS, 0, 10)
    s = ScenarioValues({"a": 2.0})

    # Other variable in __mul__/__rmul__ paths.
    q1 = x * y
    q2 = y * x
    assert q1.var1 == x
    assert q2.var1 == y

    # Expression paths in add/sub/rsub.
    e = Expression([(x, 1.0)])
    assert isinstance(x + e, Expression)
    assert isinstance(x - e, Expression)
    assert isinstance(e - x, Expression)

    # Scenario branches.
    assert isinstance(x + s, Expression)
    assert isinstance(x - s, Expression)
    assert isinstance(s - x, Expression)
