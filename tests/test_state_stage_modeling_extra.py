from polyhedron import Graph, GraphEdge, GraphNode, Model
from polyhedron.backends.compiler import compile_model
from polyhedron.modeling.element import Element


class ReservoirPeriod(Element):
    inflow = Model.ContinuousVar(min=0.0, max=10.0)
    outflow = Model.ContinuousVar(min=0.0, max=10.0)
    spill = Model.ContinuousVar(min=0.0, max=5.0)
    level = Model.ContinuousVar(min=0.0, max=20.0)

    def objective_contribution(self):
        return self.spill


class CommitmentPeriod(Element):
    commit = Model.BinaryVar()
    production = Model.ContinuousVar(min=0.0, max=5.0)

    def objective_contribution(self):
        return self.production


class ScenarioDecision(Element):
    buy = Model.ContinuousVar(min=0.0, max=10.0)
    hedge = Model.ContinuousVar(min=0.0, max=10.0)

    def objective_contribution(self):
        return 0.0


class PolicyUnit(Element):
    enabled = Model.BinaryVar()
    flow = Model.ContinuousVar(min=0.0, max=4.0)
    cluster = Model.BinaryVar()

    def objective_contribution(self):
        return self.flow


def test_state_series_builds_balances_terminal_and_bounds():
    model = Model("state-series")
    periods = [ReservoirPeriod(f"r{index}") for index in range(3)]
    model.add_elements(periods)

    series = model.state_series(periods)
    balance = series.balance(
        state_attr="level",
        initial_state=4.0,
        inflow_attr="inflow",
        outflow_attr="outflow",
        loss_attr="spill",
        name="reservoir_balance",
        group="reservoir",
    )
    link = series.link(current_attr="spill", previous_attr="outflow", lag=1, name="spill_memory")
    bounds = series.bounds(state_attr="level", lower=1.0, upper=[8.0, 7.0, 6.0], name="reservoir_bounds")
    terminal = series.terminal(state_attr="level", target=2.0, sense=">=", name="terminal_reservoir")

    compiled = compile_model(model)

    assert len(balance) == 3
    assert len(link) == 2
    assert len(bounds) == 6
    assert terminal in model.constraints
    assert len(compiled.constraints) == 12
    assert balance[0].tags == ("state", "balance")
    assert balance[0].group == "reservoir"
    assert balance[0].metadata == {"kind": "state_transition", "stage_index": 0}
    assert terminal.metadata == {"kind": "terminal_state"}


def test_window_series_builds_lags_ramps_runs_and_rolling_sums():
    model = Model("window-series")
    periods = [CommitmentPeriod(f"c{index}") for index in range(4)]
    model.add_elements(periods)

    windows = model.window_series(periods)
    lag = windows.lag_link(current_attr="production", previous_attr="production", lag=1, offset=1.0)
    rolling = windows.rolling_sum(attr="production", window=2, upper=6.0, name="energy_window")
    ramp = windows.ramp(attr="production", up=2.0, down=3.0, name="production_ramp")
    min_run = windows.min_active_run(attr="commit", minimum=2, name="min_commit_run")
    max_run = windows.max_active_run(attr="commit", maximum=2, name="max_commit_run")

    compiled = compile_model(model)

    assert len(lag) == 3
    assert len(rolling) == 3
    assert len(ramp) == 6
    assert len(min_run) == 4
    assert len(max_run) == 2
    assert len(compiled.constraints) == 18
    assert rolling[0].metadata == {"kind": "rolling_sum", "window": 2, "start": 0, "end": 1, "sense": "<="}


def test_stage_decisions_use_tree_groups_for_nonanticipativity():
    model = Model("stage-decisions")
    decisions = {name: ScenarioDecision(name) for name in ("s1", "s2", "s3", "s4")}
    model.add_elements(decisions.values())

    tree = model.scenario_tree(
        {
            "s1": ("up", "wet"),
            "s2": ("up", "dry"),
            "s3": ("down", "wet"),
            "s4": ("down", "dry"),
        },
        probabilities={"s1": 0.3, "s2": 0.2, "s3": 0.25, "s4": 0.25},
    )

    registry = model.stage_decisions()
    registry.register_many(stage=0, scenarios={name: [decision] for name, decision in decisions.items()}, attr="buy")
    registry.register_many(stage=1, scenarios={name: [decision] for name, decision in decisions.items()}, attr="hedge")

    groups_stage0 = tree.nonanticipativity_groups(0)
    groups_stage1 = tree.nonanticipativity_groups(1)
    constraints = registry.nonanticipativity(tree)
    compiled = compile_model(model)

    assert groups_stage0 == (("s1", "s2", "s3", "s4"),)
    assert groups_stage1 == (("s1", "s2"), ("s3", "s4"))
    assert len(constraints) == 5
    assert len(compiled.constraints) == 5
    assert constraints[0].group == "nonanticipativity:stage:0"
    assert constraints[0].metadata == {"kind": "stage_nonanticipativity", "stage": 0}


def test_element_policy_and_graph_helpers_cover_common_structures():
    model = Model("policy-layer")
    units = [PolicyUnit(f"u{index}") for index in range(3)]
    model.add_elements(units)

    policy = model.element_policy(units)
    totals = policy.limit_total(attr="flow", upper=5.0, lower=1.0, name="fleet_flow")
    implication = policy.imply(condition_attr="enabled", consequence_attr="flow", factor=4.0, name="unit_gate")
    sync = policy.synchronize(attr="cluster", name="cluster_sync")

    graph = Graph()
    n1 = GraphNode("n1")
    n2 = GraphNode("n2")
    n3 = GraphNode("n3")
    e1 = GraphEdge(n1, n2)
    e2 = GraphEdge(n2, n3)
    graph.add_nodes([n1, n2, n3])
    graph.add_edges([e1, e2])

    compiled = compile_model(model)

    assert len(totals) == 2
    assert len(implication) == 3
    assert len(sync) == 2
    assert len(compiled.constraints) == 7
    assert graph.out_edges(n2) == [e2]
    assert graph.in_edges(n2) == [e1]
    assert graph.successors(n2) == [n3]
    assert graph.predecessors(n2) == [n1]