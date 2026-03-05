from polyhedron import (
    AssignmentGroup,
    AssignmentOption,
    DependencyGroup,
    InventoryBucket,
    InventorySeries,
    Model,
    Resource,
    SoftConstraint,
)
from polyhedron.backends.compiler import compile_model
from polyhedron.modeling.element import Element


class ResourceTask(Element):
    usage = Model.ContinuousVar(min=0.0, max=10.0)

    def objective_contribution(self):
        return 0.0


class ScheduledStep(Element):
    start = Model.IntegerVar(min=0, max=10)
    duration = Model.IntegerVar(min=1, max=5)
    enabled = Model.BinaryVar()

    def objective_contribution(self):
        return 0.0


class DemandNode(Element):
    level = Model.ContinuousVar(min=0.0, max=10.0)

    def objective_contribution(self):
        return 0.0


def test_assignment_group_materializes_standard_constraints():
    model = Model("assignment-test")
    options = [
        AssignmentOption(subject="job_a", target="worker_1", cost=3.0),
        AssignmentOption(subject="job_a", target="worker_2", cost=2.0),
        AssignmentOption(subject="job_b", target="worker_1", cost=4.0),
        AssignmentOption(subject="job_b", target="worker_2", cost=1.0),
    ]

    group = AssignmentGroup(model=model, options=options).add_to_model()
    subject_constraints = group.assign_exactly_one()
    target_constraints = group.assign_at_most_one_per_target()
    forbidden = group.forbid("job_b", "worker_1", name="blocked_pair")

    compiled = compile_model(model)

    assert len(subject_constraints) == 2
    assert len(target_constraints) == 2
    assert forbidden.name == "blocked_pair"
    assert len(compiled.variables) == 4
    assert len(compiled.constraints) == 5
    assert len(compiled.objective_terms) == 4


def test_resource_adds_capacity_constraints_without_new_variables():
    model = Model("resource-test")
    tasks = [ResourceTask("t1"), ResourceTask("t2")]
    model.add_elements(tasks)

    resource = Resource(model=model, consumers=tasks, usage_attr="usage")
    limit = resource.limit(12.0, name="capacity")
    minimum = resource.minimum(3.0, name="minimum_load")

    compiled = compile_model(model)

    assert limit in model.constraints
    assert minimum in model.constraints
    assert len(compiled.variables) == 2
    assert len(compiled.constraints) == 2
    assert len(compiled.objective_terms) == 2


def test_inventory_series_adds_balances_and_penalty_ready_backlog():
    model = Model("inventory-test")
    buckets = [
        InventoryBucket("inv_0", backlog_penalty=5.0, track_backlog=True),
        InventoryBucket("inv_1", backlog_penalty=5.0, track_backlog=True),
        InventoryBucket("inv_2", backlog_penalty=5.0, track_backlog=True),
    ]

    series = InventorySeries(model=model, periods=buckets).add_to_model()
    balance = series.balance(initial_level=4.0)
    demand = series.meet_demand([3.0, 5.0, 2.0], use_backlog=True)
    capacity = series.capacity(10.0)
    safety = series.safety_stock(1.0)

    compiled = compile_model(model)

    assert len(balance) == 3
    assert len(demand) == 3
    assert len(capacity) == 3
    assert len(safety) == 3
    assert len(compiled.variables) == 12
    assert len(compiled.constraints) == 12
    assert len(compiled.objective_terms) == 3


def test_dependency_group_builds_binary_and_precedence_links():
    model = Model("dependency-test")
    first = ScheduledStep("first")
    second = ScheduledStep("second")
    third = ScheduledStep("third")
    model.add_elements([first, second, third])

    deps = DependencyGroup(model=model)
    requires = deps.requires(first, second, attr="enabled", name="second_needs_first")
    excludes = deps.excludes(first, third, attr="enabled", name="cannot_run_together")
    bundle = deps.all_or_nothing([first, second, third], attr="enabled", name="bundle")
    precedence = deps.precedence(
        first,
        second,
        start_attr="start",
        duration_attr="duration",
        lag=1.0,
        name="order_steps",
    )

    compiled = compile_model(model)

    assert requires in model.constraints
    assert excludes in model.constraints
    assert len(bundle) == 2
    assert precedence in model.constraints
    assert len(compiled.constraints) == 5


def test_soft_constraint_rewrites_to_bounded_penalty_slack():
    model = Model("soft-constraint-test")
    node = DemandNode("n1")
    model.add_element(node)

    soft = SoftConstraint(
        model=model,
        constraint=node.level >= 7.0,
        weight=10.0,
        name="minimum_level",
        max_violation=20.0,
    )
    relaxed = soft.add_to_model()

    compiled = compile_model(model)
    slack = soft.penalty_elements[0]
    slack_var = slack.variables["violation"]

    assert relaxed in model.constraints
    assert relaxed.sense == ">="
    assert slack_var.upper_bound == 20.0
    assert len(compiled.variables) == 2
    assert len(compiled.constraints) == 1
    assert len(compiled.objective_terms) == 2
