import builtins
from types import SimpleNamespace

import pytest

from polyhedron import Element, Model
from polyhedron.backends.types import SolveResult, SolveStatus
from polyhedron.backends.compiler import compile_model
from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression, QuadraticExpression, QuadraticTerm
from polyhedron.core.objective import (
    Objective,
    _is_scenario_values,
    _is_variable,
    flatten_weighted_objectives,
    maximize,
    minimize,
    normalize_objective_sense,
    objective,
    scale_expression_like,
)
from polyhedron.core.solution import Solution, SolveMetadata, SolutionSet, SolvedModel
from polyhedron.core.variable import VarType, Variable
from polyhedron.intelligence.branching import BranchingStrategy
from polyhedron.modeling.assignment import AssignmentGroup, AssignmentOption
from polyhedron.modeling.dependency import DependencyGroup
from polyhedron.modeling.element import Constraint as AutoConstraint
from polyhedron.modeling.graph import Graph, GraphEdge, GraphNode
from polyhedron.modeling.graph.graph_constraints import capacity_on_edges, flow_conservation
from polyhedron.modeling.inventory import InventoryBucket, InventorySeries, _get_attr as inventory_get_attr
from polyhedron.modeling.resources import Resource
from polyhedron.modeling.selection import SelectableElement, SelectionGroup
from polyhedron.modeling.soft_constraints import SoftConstraint
from polyhedron.performance import ModelTimings, timing
from polyhedron.performance.timing import TimingContext
from polyhedron.scenarios.layer import ScenarioBatchReport, ScenarioCase, ScenarioRunner, base_best_worst_cases
from polyhedron.spatial.space import DistanceMatrix, Location
from polyhedron.core.scenario import ScenarioValues
from polyhedron.units.dimensions import DIMENSIONLESS, UnitDimension, UnitRegistry, first_non_dimensionless
from polyhedron.units.validation import _to_expression, _variable_dimension, validate_model_units


class _AutoElement(Element):
    x = Model.ContinuousVar(min=0, max=5)
    y = Model.BinaryVar()

    @AutoConstraint.auto
    def upper(self):
        return self.x <= 4

    @AutoConstraint.auto
    def pair(self):
        return [self.y <= 1, self.y >= 0]


class _LegacyObjectiveElement(Element):
    x = Model.ContinuousVar(min=0, max=5)

    def objective_contribution(self):
        return self.x


class _NoneObjectiveElement(Element):
    def objective_contribution(self):
        return None


class _DecoratedObjectiveElement(Element):
    x = Model.ContinuousVar(min=0, max=5)

    @minimize(name="usage", weight=2.0, priority=1, group="ops")
    def usage_cost(self):
        return self.x


class _NoneDecoratedObjectiveElement(Element):
    @minimize(name="skip")
    def skipped(self):
        return None


class _MixedObjectiveElement(_DecoratedObjectiveElement):
    def objective_contribution(self):
        return 1.0


class _WeightedChoice(SelectableElement):
    cost: float

    def __init__(self, name: str, cost: float):
        self.cost = float(cost)
        super().__init__(name, cost=float(cost))


class _FlowEdge(GraphEdge):
    flow = Model.ContinuousVar(min=0, max=10)
    capacity = Model.ContinuousVar(min=0, max=10)


class _ValueElement(Element):
    x = Model.ContinuousVar(min=0, max=10)

    def objective_contribution(self):
        return self.x


def test_objective_and_element_branches() -> None:
    assert normalize_objective_sense(" MAXIMIZE ") == "maximize"
    with pytest.raises(ValueError, match="Unsupported objective sense"):
        normalize_objective_sense("median")
    with pytest.raises(ValueError, match="finite positive"):
        objective(weight=0.0)

    x = Variable("x", VarType.CONTINUOUS, 0, 5)
    scenario_values = ScenarioValues({"base": 3.0})
    qterm = QuadraticTerm(x, x, coefficient=2.0)
    quadratic = QuadraticExpression(linear_terms=[(x, 1.0)], quadratic_terms=[qterm], constant=1.0)

    assert isinstance(scale_expression_like(Expression([(x, 1.0)]), 1.0), Expression)
    assert scale_expression_like(Expression([(x, 1.0)], constant=2.0), 2.0).constant == 4.0
    assert scale_expression_like(qterm, 3.0).coefficient == 6.0
    assert scale_expression_like(quadratic, 2.0).constant == 2.0
    assert isinstance(scale_expression_like(x, 2.0), Expression)
    assert isinstance(scale_expression_like(3.0, 2.0), float)
    assert scale_expression_like(scenario_values, 2.0).scenario_terms[0][1] == 2.0
    with pytest.raises(TypeError, match="Unsupported objective term type"):
        scale_expression_like(object(), 2.0)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in {"polyhedron.core.scenario", "polyhedron.core.variable", "polyhedron.core.expression"}:
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(builtins, "__import__", fake_import)
    try:
        assert _is_scenario_values(object()) is False
        assert _is_variable(object()) is False
        with pytest.raises(TypeError, match="Unsupported objective term type"):
            scale_expression_like(object(), 2.0)
    finally:
        monkeypatch.undo()

    method = maximize(name="profit", weight=3.0, priority=2)

    @method
    def _profit():
        return 1.0

    assert getattr(_profit, "_polyhedron_objective").sense == "maximize"

    assert flatten_weighted_objectives([]) == ([], "minimize")
    same_terms, same_sense = flatten_weighted_objectives([legacy_objective := _LegacyObjectiveElement("a").objectives()[0]])
    assert same_sense == legacy_objective.sense
    assert len(same_terms) == 1
    mixed_terms, mixed_sense = flatten_weighted_objectives(
        [
            legacy_objective,
            SimpleNamespace(sense="maximize", expression=2.0, weight=1.5),
        ]
    )
    assert mixed_sense == "minimize"
    assert mixed_terms[1] == -3.0

    plain = Element("plain")
    assert plain.objective_contribution() == 0.0
    assert plain.objectives() == []

    auto = _AutoElement("auto")
    assert len(auto.constraints) == 3

    model = Model("objective-model")
    legacy = _LegacyObjectiveElement("legacy")
    model.add_element(legacy)
    legacy_objective = legacy.objectives()[0]
    assert legacy_objective.sense == "minimize"
    assert legacy_objective.method_name == "objective_contribution"
    assert _NoneObjectiveElement("none").objectives() == []

    decorated = _DecoratedObjectiveElement("decorated")
    decorated_objective = decorated.objectives()[0]
    assert decorated_objective.name == "usage"
    assert decorated_objective.group == "ops"
    assert _NoneDecoratedObjectiveElement("none-decorated").objectives() == []

    with pytest.raises(ValueError, match="mixes @objective-decorated methods"):
        _MixedObjectiveElement("mixed").objectives()


def test_assignment_dependency_resource_branching_and_graph_helpers() -> None:
    locked = SimpleNamespace(name="commit_var")
    BranchingStrategy(rule="name", priorities={"commit": 7}).apply(model=None, variables=[locked, object()])
    assert getattr(locked, "_branching_priority") == 7

    model = Model("business-helpers")
    subject = ["job_a"]
    target = ["worker_1"]
    options = [
        AssignmentOption(subject=subject, target=target, cost=1.0),
        AssignmentOption(subject=subject, target=["worker_2"], cost=2.0),
    ]
    group = AssignmentGroup(model=model, options=options).add_to_model()
    assert len(group.selectors()) == 2
    assert group.assign_exactly_one()[0].name.startswith("assign_exactly_one")
    assert group.assign_at_least_one()[0].name.startswith("assign_at_least_one")
    assert group.assign_at_most_one_per_target(default_capacity=2)[0].sense == "<="
    assert group.total_cost() is not None
    with pytest.raises(ValueError, match="Assignment option not found"):
        group.forbid("missing", "missing")
    with pytest.raises(TypeError, match="must be a Variable"):
        AssignmentGroup(model=model, options=options, selector_attr="cost").selectors()

    solution = Solution(
        status=SolveStatus.OPTIMAL,
        objective_value=3.0,
        values={options[0].selected: 1.0, options[1].selected: 0.0},
        solver_name="test",
    )
    solved = SolvedModel(
        model=model,
        solution=solution,
        metadata=SolveMetadata(solver_name="test", time_limit=None, mip_gap=0.01),
    )
    assert group.selected_options(solution) == [options[0]]
    assert group.selected_options(solved) == [options[0]]

    tasks = [
        SimpleNamespace(
            selected=Variable("a_sel", VarType.BINARY),
            start=Variable("a_start", VarType.CONTINUOUS, 0, 10),
            duration=2.0,
            end=Variable("a_end", VarType.CONTINUOUS, 0, 10),
            usage=Variable("a_use", VarType.CONTINUOUS, 0, 10),
        ),
        SimpleNamespace(
            selected=Variable("b_sel", VarType.BINARY),
            start=Variable("b_start", VarType.CONTINUOUS, 0, 10),
            duration=1.0,
            end=Variable("b_end", VarType.CONTINUOUS, 0, 10),
            usage=Variable("b_use", VarType.CONTINUOUS, 0, 10),
        ),
    ]
    deps = DependencyGroup(model=model)
    assert deps.requires(tasks[0], tasks[1]).sense == "<="
    assert deps.excludes(tasks[0], tasks[1]).sense == "<="
    assert deps.all_or_nothing([]) == []
    assert len(deps.all_or_nothing(tasks)) == 1
    assert deps.precedence(tasks[0], tasks[1], duration_attr="duration", lag=1.0).sense == "<="
    assert deps.precedence(tasks[0], tasks[1], end_attr=lambda item: item.end, start_attr=lambda item: item.start).sense == "<="
    with pytest.raises(ValueError, match="duration_attr or end_attr"):
        deps.precedence(tasks[0], tasks[1])

    resource = Resource(model=model, consumers=tasks, usage_attr=lambda item: item.usage)
    assert resource.total_usage([tasks[0]]) is not None
    assert resource.limit(10.0).name == "resource_limit"
    assert resource.minimum(1.0).name == "resource_minimum"
    assert resource.reserve(10.0, 2.0).name == "resource_reserve"

    n1 = GraphNode("n1")
    n2 = GraphNode("n2")
    edge = _FlowEdge(n1, n2, name="e")
    graph = Graph(nodes=[n1, n2], edges=[edge])
    assert flow_conservation(graph, n1, inflow_attr=lambda item: item.flow, outflow_attr="flow").sense == "=="
    assert len(capacity_on_edges([edge], flow_attr="flow", capacity_attr=lambda item: item.capacity)) == 1


def test_branching_fallback_compiler_skips_and_soft_equality_objective() -> None:
    class _FallbackVar:
        __slots__ = ("name", "store")

        def __init__(self, name: str):
            object.__setattr__(self, "name", name)
            object.__setattr__(self, "store", {})

        def __setattr__(self, key, value):
            if key in {"name", "store"}:
                object.__setattr__(self, key, value)
            else:
                self.store[key] = value

    fallback = _FallbackVar("commit_slot")
    BranchingStrategy(rule="name", priorities={"commit": 9}).apply(model=None, variables=[fallback])
    assert fallback.store["_branching_priority"] == 9

    with pytest.raises(ValueError, match="Temporary constraints must be Constraint instances"):
        compile_model(SimpleNamespace(elements=[], constraints=[], _temporary_constraints=[object()]))

    skipped = Objective(name="skip", sense="minimize", expression=None)
    resolved_to_none = Objective(name="gone", sense="minimize", expression=1.0)
    compiled = compile_model(
        SimpleNamespace(
            elements=[SimpleNamespace(variables={}, objectives=lambda: [skipped, resolved_to_none])],
            constraints=[],
            _temporary_constraints=[],
            _resolve_scenario_operand=lambda expr: None,
            objective_sense="maximize",
        )
    )
    assert compiled.objectives == []
    assert compiled.objective_sense == "maximize"

    model = Model("soft-equality")
    elem = _ValueElement("soft")
    model.add_element(elem)
    softened = SoftConstraint(model=model, constraint=elem.x == 3, weight=4.0, name="soft_eq").add_to_model()
    assert softened.name == "soft_eq"
    assert model.elements[-1].objective_contribution() is not None


def test_timing_scenarios_space_units_and_validation_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    timings = ModelTimings()
    timings.add("build", 1.0)
    timings.add("build", 0.5)
    assert timings.summary() == "build: 1.5000s"
    with timing(timings, "solve"):
        pass
    assert "solve" in timings.sections
    assert TimingContext(timings, "idle").__exit__(None, None, None) is False

    empty_report = ScenarioBatchReport()
    assert empty_report.best_feasible() is None
    assert empty_report.worst_feasible() is None

    report = ScenarioBatchReport(
        results=[
            SimpleNamespace(name="bad", status=SolveStatus.ERROR, objective_value=None, solve_time=0.1),
            SimpleNamespace(name="ok", status=SolveStatus.FEASIBLE, objective_value=4.0, solve_time=0.2),
            SimpleNamespace(name="best", status=SolveStatus.OPTIMAL, objective_value=2.0, solve_time=0.3),
        ]
    )
    assert report.best_feasible().name == "best"
    assert report.worst_feasible().name == "ok"
    assert "| Scenario | Status | Objective |" in report.to_markdown()

    class _RunnerModel:
        def __init__(self, should_fail: bool = False):
            self.should_fail = should_fail
            self.touched = False

        def solve(self, **kwargs):
            if self.should_fail:
                raise RuntimeError("boom")
            assert kwargs["return_solved_model"] is True
            return SimpleNamespace(status=SolveStatus.OPTIMAL, objective_value=1.5)

    models = iter([_RunnerModel(False), _RunnerModel(True)])
    runner = ScenarioRunner(lambda: next(models))
    batch = runner.run(
        [
            ScenarioCase(name="base", mutate=lambda model: setattr(model, "touched", True)),
            ScenarioCase(name="fail"),
        ],
        time_limit=5.0,
        mip_gap=0.02,
    )
    assert batch.results[0].status == SolveStatus.OPTIMAL
    assert batch.results[1].status == SolveStatus.ERROR
    assert base_best_worst_cases(best_case=lambda model: None, worst_case=lambda model: None)[1].name == "best"

    a = Location("a", 0.0, 0.0)
    b = Location("b", 1.0, 1.0)
    distances = DistanceMatrix()
    distances.set(a, b, 3.0)
    assert distances.get(a, a) == 0.0
    assert distances.get(a, b) == 3.0
    distances.add_scenario("base", weight=0.7)
    distances.add_scenario("stress")
    distances.set_scenarios(a, b, {"base": 4.0, "stress": 6.0})
    assert distances.get_scenario("base", a, b) == 4.0
    assert distances.scenarios_for(a, b) == {"base": 4.0, "stress": 6.0}
    assert distances.get_scenario_values(a, b).weights is None
    distances.add_scenario("stress", weight=0.3)
    assert distances.get_scenario_values(a, b).weights == {"base": 0.7, "stress": 0.3}

    registry = UnitRegistry.default()
    assert registry.parse(" ") == DIMENSIONLESS
    assert str(UnitDimension.from_mapping({"power": 1, "time": -1})) == "power*time^-1"
    assert str(DIMENSIONLESS) == "1"
    assert registry.parse("MW/h") == UnitDimension.from_mapping({"power": 1, "time": -1})
    assert UnitDimension.from_mapping({"x": 1}) * UnitDimension.from_mapping({"x": -1}) == DIMENSIONLESS
    assert UnitDimension.from_mapping({"power": 1}) ** 0 == DIMENSIONLESS
    assert first_non_dimensionless([DIMENSIONLESS, UnitDimension.from_mapping({"mass": 1})]).as_mapping() == {"mass": 1}
    assert first_non_dimensionless([DIMENSIONLESS]) == DIMENSIONLESS
    with pytest.raises(ValueError, match="Unknown unit symbol"):
        registry.resolve_symbol("foo")

    x = Variable("x", VarType.CONTINUOUS, unit="MW")
    y = Variable("y", VarType.CONTINUOUS, unit="h")
    z = Variable("z", VarType.CONTINUOUS)
    assert _variable_dimension(z, registry) == DIMENSIONLESS
    compiled = SimpleNamespace(
        constraints=[
            Constraint(lhs=x, sense="<=", rhs=10, name="numeric_ok"),
            Constraint(lhs=Expression([(x, 1.0), (z, 1.0), (y, 1.0)]), sense="==", rhs=0, name="bad_sum"),
            Constraint(lhs=x, sense="==", rhs=y, name="bad_compare"),
            Constraint(lhs=10, sense="==", rhs=x, name="numeric_on_lhs"),
            Constraint(lhs=Expression([(z, 0.0)]), sense="==", rhs=0, name="zero_expr"),
        ]
    )
    monkeypatch.setattr("polyhedron.units.validation.compile_model", lambda model: compiled)
    assert _to_expression(z).terms == [(z, 1.0)]
    assert _to_expression(4).constant == 4.0
    with pytest.raises(TypeError, match="Unsupported operand type"):
        _to_expression(object())
    report = validate_model_units(model=object(), registry=registry)
    assert {issue.code for issue in report.issues} == {"UNIT_INCOMPATIBLE_SUM", "UNIT_CONSTRAINT_MISMATCH"}


def test_solution_inventory_and_selection_paths() -> None:
    source_model = Model("source")
    source_elem = _ValueElement("shared")
    source_model.add_element(source_elem)
    result = SolveResult(
        status=SolveStatus.OPTIMAL,
        objective_value=2.5,
        values={source_elem.x: 3.0},
        solver_name="solver",
        reduced_costs={source_elem.x: -0.5},
        active_constraints=[],
        objective_breakdown={"base": 2.5},
        metrics={"gap": 0.0},
    )
    solution = Solution.from_solve_result(result)
    assert SolutionSet([]).primary is None
    alternatives = SolutionSet([solution])
    solved = SolvedModel(
        model=source_model,
        solution=solution,
        metadata=SolveMetadata(solver_name="solver", time_limit=1.0, mip_gap=0.01),
        alternatives=alternatives,
    )
    assert solved.get_value(source_elem.x) == 3.0
    assert solved.get_values([source_elem.x]) == {source_elem.x: 3.0}
    with pytest.raises(TypeError, match="target_model must be a Model"):
        solved.with_values(object())

    target_model = Model("target")
    target_elem = _ValueElement("shared")
    target_model.add_element(target_elem)
    transferred = solved.with_values(target_model)
    assert transferred.values[target_elem.x] == 3.0

    with pytest.raises(ValueError, match="must be finite"):
        Solution(
            status=SolveStatus.ERROR,
            objective_value=None,
            values={source_elem.x: 1.0},
            solver_name="solver",
            metrics={"gap": float("inf")},
        )

    inventory_model = Model("inventory")
    periods = [
        InventoryBucket("p0", backlog_penalty=5.0, track_backlog=True),
        InventoryBucket("p1", track_backlog=False),
    ]
    series = InventorySeries(model=inventory_model, periods=periods).add_to_model()
    assert periods[0].objective_contribution() is not None
    assert periods[1].objective_contribution() == 0.0
    assert inventory_get_attr(periods[0], lambda bucket: bucket.backlog_penalty) == 5.0
    assert len(series.balance(initial_level=2.0)) == 2
    assert len(series.meet_demand([1.0, 2.0])) == 2
    assert len(series.meet_demand(lambda period, index: index + 1, use_backlog=True, name="callable_demand")) == 2
    periods[0].demand = 4.0
    periods[1].demand = 5.0
    assert len(series.meet_demand("demand", name="attr_demand")) == 2
    assert len(series.capacity(10.0)) == 2
    assert len(series.safety_stock([0.0, 1.0])) == 2

    selection_model = Model("selection")
    items = [_WeightedChoice("a", 1.0), _WeightedChoice("b", 2.0)]
    selection = SelectionGroup(model=selection_model, elements=items).add_to_model()
    assert items[0].objective_contribution() == 0.0
    assert len(selection.selectors()) == 2
    assert selection.sum_selected() is not None
    assert selection.weighted_sum(weight_attr="cost") is not None
    assert selection.weighted_sum(weights={items[0]: 3.0}) is not None
    with pytest.raises(ValueError, match="weight_attr or weights"):
        selection.weighted_sum()
    assert selection.choose_exactly(1).name == "select_exactly"
    assert selection.choose_at_least(1).name == "select_at_least"
    assert selection.choose_at_most(1).name == "select_at_most"
    assert selection.mutually_exclusive(*items).name == "mutually_exclusive"
    assert selection.dependency(items[0], items[1]).name == "dependency"
    assert selection.budget_limit(2.0).name == "budget_limit"
    with pytest.raises(TypeError, match="must be a Variable"):
        SelectionGroup(model=selection_model, elements=items, selector_attr="cost").selectors()

    raw_values = {items[0].selected: 1.0, items[1].selected: 0.0}
    chosen = selection.selected_elements(raw_values)
    assert chosen == [items[0]]
    assert selection.selected_elements(solution) == []
    solved_selection = SolvedModel(
        model=selection_model,
        solution=Solution(
            status=SolveStatus.OPTIMAL,
            objective_value=1.0,
            values=raw_values,
            solver_name="solver",
        ),
        metadata=SolveMetadata(solver_name="solver", time_limit=None, mip_gap=0.01),
    )
    assert selection.selected_elements(solved_selection) == [items[0]]