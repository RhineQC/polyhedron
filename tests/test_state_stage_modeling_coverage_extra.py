from types import SimpleNamespace

import pytest

from polyhedron import Graph, GraphEdge, GraphNode, Model
from polyhedron.backends.compiler import compile_model
from polyhedron.core.constraint import Constraint
from polyhedron.core.variable import Variable
from polyhedron.modeling._helpers import finalize_constraint, get_attr, resolve_value
from polyhedron.modeling.element import Element
from polyhedron.modeling.policies import ElementPolicy
from polyhedron.modeling.stages import StageDecisions, _variables_from_items
from polyhedron.modeling.state import StateSeries
from polyhedron.modeling.uncertainty import ScenarioNode, ScenarioTree, ScenarioTreeBuilder, chance_constraint, cvar, nonanticipativity, worst_case
from polyhedron.modeling.windows import WindowSeries


class StatePeriod(Element):
    state = Model.ContinuousVar(min=0.0, max=10.0)
    inflow = Model.ContinuousVar(min=0.0, max=4.0)
    outflow = Model.ContinuousVar(min=0.0, max=4.0)
    active = Model.BinaryVar()
    load = Model.ContinuousVar(min=0.0, max=5.0)

    def objective_contribution(self):
        return 0.0


class DecisionElement(Element):
    first = Model.ContinuousVar(min=0.0, max=10.0)
    second = Model.ContinuousVar(min=0.0, max=10.0)

    def objective_contribution(self):
        return 0.0


def test_helper_functions_cover_callable_sequence_and_string_paths():
    item = SimpleNamespace(value=7.0, factor=2.0)
    constraint = finalize_constraint(
        Constraint(lhs=1, sense="==", rhs=1),
        base_name="base",
        tags=("alpha",),
        source="tests",
        unit="MW",
        relaxable=True,
        metadata={"kind": "demo"},
    )

    assert get_attr(item, "value") == 7.0
    assert get_attr(item, lambda obj: obj.factor + 1.0) == 3.0
    assert resolve_value([1.0, 2.0], item, 1) == 2.0
    assert resolve_value("value", item, 0) == 7.0
    assert resolve_value(lambda obj, index: obj.factor + index, item, 2) == 4.0
    assert constraint.unit == "MW"
    assert constraint.relaxable is True
    assert constraint.metadata == {"kind": "demo"}


def test_state_series_covers_add_to_model_transition_and_error_paths():
    model = Model("state-coverage")
    periods = [StatePeriod(f"p{index}") for index in range(2)]
    filtered_series = StateSeries(model, (periods[0], object(), periods[1])).add_to_model()
    series = StateSeries(model, tuple(periods))

    transition = series.transition(
        state_attr="state",
        initial_state=1.0,
        update=lambda period, index: period.inflow - period.outflow + index,
        previous_weight=0.5,
        metadata={"custom": True},
    )
    lower_only = series.bounds(state_attr="state", lower=0.0, name="state_floor")
    equal_terminal = StateSeries(model, tuple(periods)).terminal(state_attr="state", target=1.0, sense="==")
    upper_terminal = StateSeries(model, tuple(periods)).terminal(state_attr="state", target=9.0, sense="<=")

    assert filtered_series is not None
    assert len(model.elements) == 2
    assert len(transition) == 2
    assert len(lower_only) == 2
    assert transition[0].metadata == {"kind": "state_transition", "stage_index": 0, "custom": True}
    assert equal_terminal.sense == "=="
    assert upper_terminal.sense == "<="

    with pytest.raises(ValueError, match="lag"):
        StateSeries(model, tuple(periods)).link(current_attr="state", previous_attr="state", lag=0)
    with pytest.raises(ValueError, match="requires at least one period"):
        StateSeries(model, ()).terminal(state_attr="state", target=0.0)
    with pytest.raises(ValueError, match="sense"):
        StateSeries(model, tuple(periods)).terminal(state_attr="state", target=0.0, sense="!=")


def test_window_series_covers_lower_equal_and_guard_paths():
    model = Model("window-coverage")
    periods = [StatePeriod(f"w{index}") for index in range(3)]
    filtered_series = WindowSeries(model, (periods[0], "skip", periods[1], periods[2])).add_to_model()
    series = WindowSeries(model, tuple(periods))

    rolling = series.rolling_sum(attr="load", window=2, lower=1.0, equal=2.0, metadata={"x": 1})
    max_run_empty = WindowSeries(model, tuple(periods[:2])).max_active_run(attr="active", maximum=2)

    assert filtered_series is not None
    assert len(model.elements) == 3
    assert len(rolling) == 4
    assert rolling[0].metadata == {"kind": "rolling_sum", "window": 2, "start": 0, "end": 1, "x": 1, "sense": ">="}
    assert rolling[1].metadata == {"kind": "rolling_sum", "window": 2, "start": 0, "end": 1, "x": 1, "sense": "=="}
    assert max_run_empty == []

    with pytest.raises(ValueError, match="lag"):
        WindowSeries(model, tuple(periods)).lag_link(current_attr="load", previous_attr="load", lag=0)
    with pytest.raises(ValueError, match="window"):
        WindowSeries(model, tuple(periods)).rolling_sum(attr="load", window=0, upper=1.0)
    with pytest.raises(ValueError, match="minimum"):
        WindowSeries(model, tuple(periods)).min_active_run(attr="active", minimum=0)
    with pytest.raises(ValueError, match="maximum"):
        WindowSeries(model, tuple(periods)).max_active_run(attr="active", maximum=0)


def test_policy_layer_covers_equal_where_and_empty_sync():
    model = Model("policy-coverage")
    periods = [StatePeriod(f"u{index}") for index in range(3)]
    model.add_elements(periods)
    policy = ElementPolicy(model=model, elements=tuple(periods))

    equality = policy.limit_total(
        attr="load",
        equal=2.0,
        where=lambda element: element.name != "u2",
        name="exact_load",
    )
    implications = policy.imply(
        condition_attr="active",
        consequence_attr="load",
        factor=5.0,
        where=lambda element: element.name == "u1",
    )
    empty_sync = policy.synchronize(attr="active", where=lambda element: element.name == "missing")

    assert len(equality) == 1
    assert equality[0].metadata == {"kind": "policy_total_equal"}
    assert len(implications) == 1
    assert implications[0].index_key == 1
    assert empty_sync == []


def test_stage_decisions_cover_registration_filters_and_errors():
    model = Model("stage-coverage")
    left = DecisionElement("left")
    right = DecisionElement("right")
    model.add_elements([left, right])
    registry = StageDecisions(model)

    decision = registry.register(scenario="s1", stage=0, items=[left], attr="first", label="root")
    many = registry.register_many(stage=1, scenarios={"s1": [left], "s2": [right]}, attr="second")
    nested = _variables_from_items([[left.first, right.second]], None)

    assert decision.label == "root"
    assert len(many) == 2
    assert nested == (left.first, right.second)
    assert registry.by_stage(1) == tuple(many)

    with pytest.raises(ValueError, match="non-negative"):
        registry.register(scenario="s1", stage=-1, items=[left], attr="first")
    with pytest.raises(TypeError, match="Variable instances"):
        _variables_from_items([SimpleNamespace(first=1.0)], "first")
    with pytest.raises(TypeError, match="Variable instances"):
        _variables_from_items([[left.first, object()]], None)
    with pytest.raises(TypeError, match="Variable instances"):
        _variables_from_items([object()], None)

    tree = ScenarioTreeBuilder.from_paths({"s1": ("up",), "s2": ("down",)})
    filtered = registry.nonanticipativity(tree, stages=[2])
    assert filtered == []

    single_registry = StageDecisions(model)
    single_registry.register(scenario="s1", stage=0, items=[left], attr="first")
    assert single_registry.nonanticipativity(tree) == []


def test_uncertainty_tree_helpers_and_builders_cover_branch_paths():
    tree = ScenarioTree(
        nodes=(
            ScenarioNode("root", stage=0, metadata={"scenario": "root"}),
            ScenarioNode("root/up", stage=1, parent="root"),
            ScenarioNode("root/down", stage=1, parent="root"),
            ScenarioNode("leaf_a", stage=2, parent="root/up", metadata={"scenario": "A"}),
            ScenarioNode("leaf_b", stage=2, parent="root/down"),
        )
    )

    assert tree.leaves()[-1].name == "leaf_b"
    assert tree.stage(1)[0].name == "root/up"
    assert tree.children("root") == (tree.node("root/up"), tree.node("root/down"))
    assert [node.name for node in tree.ancestors("leaf_a", include_self=True)] == ["root", "root/up", "leaf_a"]
    assert [node.name for node in tree.descendant_leaves("root")] == ["leaf_a", "leaf_b"]
    assert tree.leaf_scenarios() == ("A", "leaf_b")
    assert tree.nonanticipativity_groups(1, scenarios={"A"}) == (("A",),)

    with pytest.raises(KeyError, match="Unknown scenario node"):
        tree.node("missing")
    with pytest.raises(ValueError, match="must not be empty"):
        ScenarioTreeBuilder.from_paths({})
    with pytest.raises(ValueError, match="at least one branch label"):
        ScenarioTreeBuilder.from_paths({"s1": ()})
    with pytest.raises(ValueError, match="at least one stage"):
        ScenarioTreeBuilder.from_branching(())
    with pytest.raises(ValueError, match="positive"):
        ScenarioTreeBuilder.from_branching((2, 0))

    built = ScenarioTreeBuilder.from_branching((2, 2), prefix="p")
    assert len(built.leaf_scenarios()) == 4
    assert built.node("root").probability == pytest.approx(1.0)


def test_uncertainty_primitives_cover_default_probability_and_error_paths():
    model = Model("uncertainty-primitives")
    left = DecisionElement("u1")
    right = DecisionElement("u2")
    model.add_elements([left, right])

    bound = worst_case(model, {"base": left.first, "stress": 2.0 * right.first}, name="worst")
    tail = cvar(model, {"base": left.first, "stress": right.first}, alpha=0.5, name="tail")
    linked = nonanticipativity(model, {"base": [left.first], "stress": [right.first]}, groups=[("base",), ("base", "stress")])
    chance = chance_constraint(
        model,
        {"base": left.first <= 1.0, "stress": right.first <= 2.0},
        max_violation_probability=0.5,
        name="chance",
    )
    compiled = compile_model(model)

    assert bound.name == "worst"
    assert tail.constant == 0.0
    assert len(linked) == 1
    assert chance[-1].name == "chance:budget"
    assert len(compiled.constraints) >= 5

    with pytest.raises(ValueError, match="alpha"):
        cvar(model, {"base": left.first}, alpha=1.0, name="bad_tail")
    with pytest.raises(ValueError, match="equal-length"):
        nonanticipativity(model, {"base": [left.first], "stress": [right.first, right.second]}, groups=[("base", "stress")])
    with pytest.raises(ValueError, match="between 0 and 1"):
        chance_constraint(model, {"base": left.first <= 1.0}, max_violation_probability=2.0)


def test_graph_objective_methods_and_helper_navigation_cover_remaining_lines():
    graph = Graph()
    source = GraphNode("source")
    target = GraphNode("target")
    edge = GraphEdge(source, target)
    graph.add_node(source)
    graph.add_edge(edge)

    assert source.objective_contribution() == 0
    assert edge.objective_contribution() == 0
    assert graph.in_edges(source) == []
    assert graph.out_edges(source) == [edge]
    assert graph.predecessors(target) == [source]
    assert graph.successors(source) == [target]