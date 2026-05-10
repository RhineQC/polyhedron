import builtins

import pytest

from polyhedron import Element, Model
from polyhedron.core.expression import (
    Expression,
    QuadraticExpression,
    QuadraticTerm,
    evaluate_expression,
    expression_bounds,
)
from polyhedron.core.scenario import ScenarioValues
from polyhedron.core.variable import VarType, Variable
from polyhedron.modeling.indexing import (
    IndexedElement,
    IndexSet,
    Param,
    VarArray,
    _VariableCarrier,
    _label_key,
    sum_over,
    where,
)
from polyhedron.modeling.transforms import (
    _as_expression,
    _big_m_for_constraint,
    add_sos1,
    add_sos2,
    disjunction,
    indicator,
    piecewise_cost,
    piecewise_linear,
)


class _TransformElement(Element):
    x = Model.ContinuousVar(min=-2, max=6)
    y = Model.ContinuousVar(min=0, max=5)
    z = Model.BinaryVar()

    def objective_contribution(self):
        return self.x + self.y


class _IndexedElement(Element):
    load = Model.ContinuousVar(min=0, max=10)

    def objective_contribution(self):
        return self.load


def test_expression_and_quadratic_operation_branches() -> None:
    x = Variable("x", VarType.CONTINUOUS, -2, 3)
    y = Variable("y", VarType.CONTINUOUS, 1, 4)
    expr = Expression([(x, 2.0)], constant=1.0)
    qterm = QuadraticTerm(x, y, coefficient=3.0)
    quadratic = QuadraticExpression(linear_terms=[(y, -1.0)], quadratic_terms=[qterm], constant=2.0)
    scenarios = ScenarioValues({"lo": -1.0, "hi": 3.0})

    assert isinstance(expr + quadratic, QuadraticExpression)
    assert isinstance(expr + qterm, QuadraticExpression)
    assert isinstance(expr - quadratic, QuadraticExpression)
    assert isinstance(expr - qterm, QuadraticExpression)

    assert isinstance(expr.__rsub__(quadratic), QuadraticExpression)
    assert isinstance(expr.__rsub__(qterm), QuadraticExpression)
    assert isinstance(expr.__rsub__(Expression([(y, 1.0)])), Expression)
    assert isinstance(expr.__rsub__(y), Expression)
    assert isinstance(expr.__rsub__(scenarios), Expression)

    assert isinstance(expr * y, QuadraticExpression)
    assert isinstance(expr * Expression([(y, 4.0)], constant=3.0), QuadraticExpression)
    with pytest.raises(TypeError, match="Scenario-aware expressions cannot be multiplied"):
        Expression.from_scenario(scenarios) * Expression([(x, 1.0)])
    assert expr.__mul__(object()) is NotImplemented

    assert expr.resolve_scenarios() is expr
    assert expr.scenario_names() is None
    assert (expr >= 0).sense == ">="
    assert (expr == 0).sense == "=="

    assert isinstance(qterm + 1, QuadraticExpression)
    assert isinstance(1 + qterm, QuadraticExpression)
    assert isinstance(qterm - 1, QuadraticExpression)
    assert isinstance(1 - qterm, QuadraticExpression)

    assert isinstance(quadratic + QuadraticExpression(constant=1.0), QuadraticExpression)
    assert isinstance(quadratic + qterm, QuadraticExpression)
    assert isinstance(quadratic + Expression([(x, 1.0)], constant=2.0), QuadraticExpression)
    assert isinstance(quadratic + x, QuadraticExpression)
    assert isinstance(quadratic + 1, QuadraticExpression)
    assert quadratic.__add__(object()) is NotImplemented
    assert isinstance(quadratic.__radd__(1), QuadraticExpression)

    assert isinstance(quadratic - QuadraticExpression(constant=1.0), QuadraticExpression)
    assert isinstance(quadratic - qterm, QuadraticExpression)
    assert isinstance(quadratic - Expression([(x, 1.0)]), QuadraticExpression)
    assert isinstance(quadratic - x, QuadraticExpression)
    assert isinstance(quadratic - 1, QuadraticExpression)
    assert quadratic.__sub__(object()) is NotImplemented
    assert isinstance(5 - quadratic, QuadraticExpression)

    scaled = quadratic * 2
    assert scaled.constant == 4.0
    assert isinstance(2 * quadratic, QuadraticExpression)
    assert (-quadratic).constant == -2.0
    assert (quadratic <= 0).sense == "<="
    assert (quadratic >= 0).sense == ">="
    assert (quadratic == 0).sense == "=="


def test_expression_bounds_and_evaluation_cover_remaining_paths() -> None:
    x = Variable("x", VarType.CONTINUOUS, -2, 3)
    y = Variable("y", VarType.CONTINUOUS, 1, 4)
    qterm = QuadraticTerm(x, y, coefficient=-2.0)
    cubic = x**3
    quadratic = QuadraticExpression(linear_terms=[(x, 2.0)], quadratic_terms=[qterm], constant=1.0)
    scenario_expr = Expression(
        [(x, 1.0)],
        constant=1.0,
        scenario_terms=[(ScenarioValues({"a": -2.0, "b": 5.0}), 2.0)],
    )

    assert expression_bounds(4) == (4.0, 4.0)
    assert expression_bounds(x) == (-2.0, 3.0)
    assert expression_bounds(cubic) == (-8.0, 27.0)
    assert expression_bounds(qterm) == (-24.0, 16.0)
    assert expression_bounds(quadratic) == (-27.0, 23.0)
    assert expression_bounds(scenario_expr) == (-5.0, 14.0)

    values = {x: 2.0, y: 3.0}
    assert evaluate_expression(2, values) == 2.0
    assert evaluate_expression(x, values) == 2.0
    assert evaluate_expression(qterm, values) == -12.0
    assert evaluate_expression(quadratic, values) == -7.0

    expected_expr = Expression(
        [(x, 1.0)],
        constant=1.0,
        scenario_terms=[(ScenarioValues({"a": 2.0, "b": 6.0}), 0.5)],
    )
    assert evaluate_expression(expected_expr, {x: 2.0}) == 5.0

    with pytest.raises(TypeError, match="Unsupported expression type for bounds"):
        expression_bounds(object())
    with pytest.raises(TypeError, match="Unsupported expression type for evaluation"):
        evaluate_expression(object(), values)


def test_variable_operator_and_import_fallback_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    x = Variable("x", VarType.CONTINUOUS, 0, 10)
    y = Variable("y", VarType.CONTINUOUS, 0, 5)
    expr = Expression([(y, 2.0)], constant=1.0)
    quadratic = QuadraticExpression(linear_terms=[(y, 1.0)], constant=4.0)
    scenarios = ScenarioValues({"base": 2.0})

    assert (x * 3).terms == [(x, 3)]
    assert isinstance(x * expr, QuadraticExpression)
    assert isinstance(x.__rmul__(y), QuadraticTerm)
    assert isinstance(x.__rmul__(expr), QuadraticExpression)
    assert isinstance(x.__rsub__(y), Expression)
    assert isinstance(x.__rsub__(expr), Expression)
    assert isinstance(x.__rsub__(scenarios), Expression)

    with pytest.raises(TypeError, match="Quadratic expressions cannot be multiplied"):
        x * quadratic
    with pytest.raises(TypeError, match="Quadratic expressions cannot be multiplied"):
        x.__rmul__(quadratic)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "polyhedron.core.scenario":
            raise ImportError("blocked scenario")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert (x + 4).constant == 4.0
    assert (x - 4).constant == -4.0
    assert (7 - x).constant == 7.0
    assert (x >= 1).sense == ">="
    assert (x == 1).sense == "=="


def test_indexing_helpers_and_collections_cover_remaining_paths() -> None:
    assert _label_key(("north", (1, "peak"))) == "north,1,peak"

    periods = IndexSet("period", [1, 2, 3])
    scenarios = IndexSet("scenario", ["base", "stress"])
    assert tuple(iter(periods)) == (1, 2, 3)
    assert len(periods) == 3
    assert 2 in periods
    assert periods.where(lambda item: item > 1, name="tail").items == (2, 3)
    assert periods.map(lambda item: item * 10) == (10, 20, 30)
    assert periods.product(scenarios).name == "period x scenario"
    assert periods.product(scenarios, name="pairs").name == "pairs"

    param = Param("demand", {1: 5}, index_set=periods, default=0)
    assert param[1] == 5
    assert param[2] == 0
    assert param.get(1) == 5
    assert param.get(2) == 0
    assert param.get(99, default=7) == 7
    assert param.items_view() == ((1, 5), (2, 0), (3, 0))
    assert Param("raw", {"a": 1}).items_view() == (("a", 1),)
    with pytest.raises(KeyError):
        Param("missing", {1: 1})[2]

    carrier = _VariableCarrier("carrier", {"x": Variable("cx", VarType.CONTINUOUS)})
    assert carrier.objective_contribution() == 0.0

    model = Model("indexing")
    pair_index = IndexSet("pairs", [("n", 1), ("s", 2)])
    array = VarArray.build(
        model=model,
        name="dispatch",
        index_set=pair_index,
        var_type=VarType.INTEGER,
        lower_bound=0,
        upper_bound=5,
        unit="MW",
    )
    assert array[("n", 1)].name == "dispatch[n,1]"
    assert tuple(key for key, _var in array.items()) == pair_index.items
    assert array.keys() == pair_index.items
    assert len(array.values()) == 2
    assert array.where(lambda key: key[0] == "n").keys() == (("n", 1),)
    assert isinstance(array.sum(), Expression)
    assert isinstance(array.sum(lambda key, var: key[1] * var), Expression)

    indexed = IndexedElement.build(
        name="jobs",
        index_set=periods,
        factory=lambda key: _IndexedElement(f"job_{key}"),
    )
    assert indexed[1].name == "job_1"
    assert len(indexed.values()) == 3
    assert indexed.add_to_model(model) is indexed

    assert sum_over(periods, lambda item: item, where=lambda item: item % 2 == 1) == 4.0
    assert where(periods, lambda item: item >= 2) == (2, 3)


def test_transform_error_and_disjunction_paths() -> None:
    model = Model("transform_branches")
    elem = _TransformElement("e1")
    model.add_element(elem)

    quadratic_term = elem.x * elem.y
    quadratic = QuadraticExpression(linear_terms=[(elem.x, 1.0)], quadratic_terms=[quadratic_term], constant=1.0)
    linear = Expression([(elem.x, 1.0)], constant=2.0)

    assert _as_expression(quadratic) is quadratic
    assert _as_expression(linear) is linear
    assert isinstance(_as_expression(quadratic_term), QuadraticExpression)
    assert isinstance(_as_expression(elem.x), Expression)
    assert _as_expression(5).constant == 5.0

    assert _big_m_for_constraint(elem.x <= 3) >= 0.0
    assert _big_m_for_constraint(elem.x >= 1) >= 0.0
    assert _big_m_for_constraint(elem.x == 2) >= 0.0

    with pytest.raises(ValueError, match="at least one expression"):
        model.max_var([], name="empty_max")
    with pytest.raises(ValueError, match="at least one expression"):
        model.min_var([], name="empty_min")
    with pytest.raises(TypeError, match="binary control variable"):
        indicator(model, elem.x, elem.x <= 1, name="bad_indicator")
    with pytest.raises(ValueError, match="active_value must be 0 or 1"):
        indicator(model, elem.z, elem.x <= 1, name="bad_active", active_value=2)

    ge_constraints = indicator(model, elem.z, elem.x >= 1, name="gate_ge", active_value=0, big_m=8)
    eq_constraints = indicator(model, elem.z, elem.x == 2, name="gate_eq")
    assert len(ge_constraints) == 1
    assert len(eq_constraints) == 2

    assert add_sos1(model, [], name="empty_sos1") == []
    with pytest.raises(ValueError, match="at least two variables"):
        add_sos2(model, [elem.x], name="bad_sos2")
    with pytest.raises(ValueError, match="identical length"):
        piecewise_linear(model, name="bad_len", input_var=elem.x, breakpoints=[0, 1], values=[0])
    with pytest.raises(ValueError, match="at least two breakpoints"):
        piecewise_linear(model, name="bad_breakpoints", input_var=elem.x, breakpoints=[0], values=[0])

    cost = piecewise_cost(model, name="energy_cost", input_var=elem.x, breakpoints=[0, 5], costs=[0, 10])
    selectors = disjunction(
        model,
        [[elem.x <= 4], [elem.y >= 2, elem.x + elem.y == 5]],
        name="choose_mode",
        big_m=10,
    )
    assert cost.name == "energy_cost"
    assert len(selectors) == 2