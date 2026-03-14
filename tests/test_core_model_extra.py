import pytest

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression
from polyhedron.core.model import Model
from polyhedron.core.scenario import ScenarioValues
from polyhedron.modeling.element import Element
from polyhedron.modeling.graph import Graph, GraphEdge, GraphNode
from polyhedron.temporal.time_horizon import TimeHorizon


class MNode(GraphNode):
    pass


class MEdge(GraphEdge):
    pass


class Mini(Element):
    def __init__(self, name, val):
        super().__init__(name, val=val)

    def objective_contribution(self):
        return 0


def test_model_graph_horizon_schedule_and_deferred_constraints() -> None:
    model = Model("m")
    a = MNode("A")
    b = MNode("B")
    g = Graph(nodes=[a, b], edges=[MEdge(a, b)])
    model.add_graph(g)
    assert len(model.elements) == 3

    h = model.TimeHorizon(2)
    assert isinstance(h, TimeHorizon)

    schedule = model.Schedule([Mini("n", 1)], h)
    assert len(schedule) == 1
    assert len(model.elements) >= 5

    @model.constraint(name="deferred")
    def deferred():
        return [Constraint(lhs=1, sense="<=", rhs=2, name=None), Constraint(lhs=1, sense=">=", rhs=0, name=None)]

    model.materialize_constraints()
    assert any(c.name == "deferred" for c in model.constraints)


def test_model_scenario_expansion_expected_and_robust_and_mismatch() -> None:
    model = Model("s")
    s1 = ScenarioValues({"a": 1.0, "b": 2.0})
    s2 = ScenarioValues({"a": 3.0, "b": 4.0})

    cons = Constraint(lhs=Expression.from_scenario(s1), sense="<=", rhs=Expression.from_scenario(s2), name="c")
    expanded = model._expand_scenario_constraint(cons)
    assert len(expanded) == 1

    model.scenario_policy = "robust"
    expanded2 = model._expand_scenario_constraint(cons)
    assert len(expanded2) == 2
    assert {c.name for c in expanded2} == {"c:a", "c:b"}

    c_bad = Constraint(
        lhs=Expression.from_scenario(ScenarioValues({"x": 1.0})),
        sense="<=",
        rhs=Expression.from_scenario(ScenarioValues({"y": 1.0})),
        name="bad",
    )
    with pytest.raises(ValueError, match="Scenario sets must match"):
        model._expand_scenario_constraint(c_bad)


def test_model_resolve_scenario_operand_and_branching_priority_failure() -> None:
    s = ScenarioValues({"a": 2.0, "b": 4.0})
    expr = Expression.from_scenario(s)

    out_expr = Model._resolve_scenario_operand(expr)
    out_s = Model._resolve_scenario_operand(s)
    out_n = Model._resolve_scenario_operand(3)

    assert isinstance(out_expr, Expression)
    assert out_s == 3.0
    assert out_n == 3

    class E(Element):
        x = Model.ContinuousVar(min=0)

        def __init__(self, name):
            super().__init__(name)

        def objective_contribution(self):
            return self.x

    m = Model("bp")
    e = E("e")
    m.add_element(e)

    with pytest.raises(Exception):
        m.branching_priority([e.x], 1)
