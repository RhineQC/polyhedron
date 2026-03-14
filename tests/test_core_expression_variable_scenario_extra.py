import pytest

from polyhedron.core.expression import Expression
from polyhedron.core.scenario import ScenarioValues
from polyhedron.core.variable import VarType, Variable, VariableDefinition


def _x():
    return Variable("x", VarType.CONTINUOUS, 0, 10)


def _y():
    return Variable("y", VarType.INTEGER, 0, 5)


def test_variable_arithmetic_and_quadratic() -> None:
    x = _x()
    y = _y()

    q = x * y
    assert q.var1 == x
    assert q.var2 == y

    q2 = x ** 3
    assert q2.power == 3

    expr = -x + y - 2
    assert isinstance(expr, Expression)
    assert expr.constant == -2.0


def test_variable_scenario_ops_cover_try_paths() -> None:
    x = _x()
    s = ScenarioValues({"a": 2, "b": 4}, weights={"a": 1, "b": 3})

    e1 = x + s
    e2 = x - s
    e3 = s - x

    assert len(e1.scenario_terms) == 1
    assert len(e2.scenario_terms) == 1
    assert isinstance(e3, Expression)


def test_expression_add_sub_rsub_with_variable_and_scenario() -> None:
    x = _x()
    s = ScenarioValues({"s1": 1.0, "s2": 3.0})

    expr = Expression([(x, 2.0)], constant=1.0)
    out = expr + x + s - x - s
    assert isinstance(out, Expression)

    back = 10 - expr
    assert isinstance(back, Expression)
    assert back.constant == 9.0


def test_expression_scenario_resolution_and_name_checks() -> None:
    s1 = ScenarioValues({"a": 1.0, "b": 3.0})
    s2 = ScenarioValues({"a": 2.0, "b": 6.0})
    expr = Expression.from_scenario(s1) + Expression.from_scenario(s2)

    names = expr.scenario_names()
    assert names == {"a", "b"}

    resolved_a = expr.resolve_scenario("a")
    assert resolved_a.constant == 3.0

    expected = expr.resolve_scenarios()
    assert pytest.approx(expected.constant) == (1.0 + 3.0) / 2.0 + (2.0 + 6.0) / 2.0


def test_expression_scenario_name_mismatch_raises() -> None:
    s1 = ScenarioValues({"a": 1.0})
    s2 = ScenarioValues({"b": 2.0})
    expr = Expression.from_scenario(s1) + Expression.from_scenario(s2)

    with pytest.raises(ValueError, match="Scenario sets must match"):
        expr.scenario_names()


def test_scenario_values_expected_value_error_paths_and_constraints() -> None:
    with pytest.raises(ValueError, match="at least one scenario"):
        ScenarioValues({}).expected_value()

    s = ScenarioValues({"a": 1.0}, weights={})
    with pytest.raises(ValueError, match="Missing weights"):
        s.expected_value()

    s2 = ScenarioValues({"a": 1.0}, weights={"a": 0.0})
    with pytest.raises(ValueError, match="positive value"):
        s2.expected_value()

    s3 = ScenarioValues({"a": 2.0, "b": 4.0})
    assert s3.value_for("a") == 2.0
    assert s3.scenario_names() == {"a", "b"}

    c1 = s3 <= 5
    c2 = s3 >= 1
    c3 = s3 == 3
    assert c1.sense == "<="
    assert c2.sense == ">="
    assert c3.sense == "=="


def test_variable_definition_create_variable() -> None:
    vd = VariableDefinition(VarType.INTEGER, min=1, max=7, unit="MW")
    v = vd.create_variable("z")
    assert v.name == "z"
    assert v.var_type == VarType.INTEGER
    assert v.lower_bound == 1
    assert v.upper_bound == 7
    assert v.unit == "MW"
