from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import expression_bounds
from polyhedron.core.variable import VarType, Variable


@dataclass(frozen=True)
class ScenarioNode:
    name: str
    stage: int
    probability: float = 1.0
    parent: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioTree:
    nodes: tuple[ScenarioNode, ...]

    def leaves(self) -> tuple[ScenarioNode, ...]:
        parent_names = {node.parent for node in self.nodes if node.parent is not None}
        return tuple(node for node in self.nodes if node.name not in parent_names)

    def stage(self, level: int) -> tuple[ScenarioNode, ...]:
        return tuple(node for node in self.nodes if node.stage == level)

    def node(self, name: str) -> ScenarioNode:
        for node in self.nodes:
            if node.name == name:
                return node
        raise KeyError(f"Unknown scenario node '{name}'.")

    def children(self, name: str) -> tuple[ScenarioNode, ...]:
        return tuple(node for node in self.nodes if node.parent == name)

    def ancestors(self, name: str, *, include_self: bool = False) -> tuple[ScenarioNode, ...]:
        lineage: list[ScenarioNode] = []
        current = self.node(name)
        if include_self:
            lineage.append(current)
        while current.parent is not None:
            current = self.node(current.parent)
            lineage.append(current)
        return tuple(reversed(lineage))

    def descendant_leaves(self, name: str) -> tuple[ScenarioNode, ...]:
        leaves: list[ScenarioNode] = []
        pending = [self.node(name)]
        while pending:
            current = pending.pop()
            children = self.children(current.name)
            if not children:
                leaves.append(current)
                continue
            pending.extend(children)
        return tuple(sorted(leaves, key=lambda item: item.name))

    def leaf_scenarios(self) -> tuple[str, ...]:
        return tuple(self._scenario_id(leaf) for leaf in self.leaves())

    def nonanticipativity_groups(
        self,
        stage: int,
        *,
        scenarios: Iterable[str] | None = None,
    ) -> tuple[tuple[str, ...], ...]:
        scenario_filter = None if scenarios is None else set(scenarios)
        groups: list[tuple[str, ...]] = []
        for node in self.stage(stage):
            scenario_group = tuple(
                sorted(
                    scenario
                    for scenario in (self._scenario_id(leaf) for leaf in self.descendant_leaves(node.name))
                    if scenario_filter is None or scenario in scenario_filter
                )
            )
            if scenario_group:
                groups.append(scenario_group)
        return tuple(sorted(groups))

    @staticmethod
    def _scenario_id(node: ScenarioNode) -> str:
        scenario = node.metadata.get("scenario")
        return str(scenario) if scenario is not None else node.name


class ScenarioTreeBuilder:
    @staticmethod
    def from_paths(
        scenario_paths: Mapping[str, Sequence[str]],
        *,
        probabilities: Mapping[str, float] | None = None,
    ) -> ScenarioTree:
        if not scenario_paths:
            raise ValueError("scenario_paths must not be empty.")
        default_probability = 1.0 / len(scenario_paths)
        leaf_probabilities = {
            scenario: float((probabilities or {}).get(scenario, default_probability))
            for scenario in scenario_paths
        }
        nodes: dict[str, ScenarioNode] = {
            "root": ScenarioNode(name="root", stage=0, probability=1.0, parent=None, metadata={"root": True})
        }
        for scenario, path in scenario_paths.items():
            if not path:
                raise ValueError("Each scenario path must contain at least one branch label.")
            parent = "root"
            for stage_index, label in enumerate(path[:-1], start=1):
                node_name = f"{parent}/{label}"
                if node_name not in nodes:
                    nodes[node_name] = ScenarioNode(
                        name=node_name,
                        stage=stage_index,
                        probability=0.0,
                        parent=parent,
                        metadata={"branch": label},
                    )
                parent = node_name
            leaf_stage = len(path)
            nodes[scenario] = ScenarioNode(
                name=scenario,
                stage=leaf_stage,
                probability=leaf_probabilities[scenario],
                parent=parent,
                metadata={"scenario": scenario, "branch": path[-1]},
            )
        aggregated = dict(leaf_probabilities)
        ordered_nodes = sorted(nodes.values(), key=lambda node: node.stage, reverse=True)
        for node in ordered_nodes:
            if node.name == "root":
                continue
            parent = node.parent
            if parent is not None:
                aggregated[parent] = aggregated.get(parent, 0.0) + aggregated.get(node.name, node.probability)
        updated_nodes = []
        for node in nodes.values():
            updated_nodes.append(
                ScenarioNode(
                    name=node.name,
                    stage=node.stage,
                    probability=aggregated.get(node.name, node.probability),
                    parent=node.parent,
                    metadata=node.metadata,
                )
            )
        return ScenarioTree(tuple(sorted(updated_nodes, key=lambda item: (item.stage, item.name))))

    @staticmethod
    def from_branching(
        branching: Sequence[int],
        *,
        prefix: str = "scenario",
    ) -> ScenarioTree:
        if not branching:
            raise ValueError("branching must contain at least one stage.")
        paths: dict[str, tuple[str, ...]] = {}
        partial_paths = [tuple()]
        for stage_index, width in enumerate(branching, start=1):
            if width <= 0:
                raise ValueError("Each branching width must be positive.")
            next_paths: list[tuple[str, ...]] = []
            for partial in partial_paths:
                for branch_index in range(width):
                    next_paths.append(partial + (f"stage{stage_index}_b{branch_index}",))
            partial_paths = next_paths
        for scenario_index, path in enumerate(partial_paths):
            paths[f"{prefix}_{scenario_index}"] = path
        return ScenarioTreeBuilder.from_paths(paths)


def worst_case(model, scenario_values: Mapping[str, object], *, name: str):
    bounds = [expression_bounds(value) for value in scenario_values.values()]
    lower = min(bound[0] for bound in bounds)
    upper = max(bound[1] for bound in bounds)
    bound = model.add_variable(name, lower_bound=lower, upper_bound=upper)
    for scenario_name, expr in scenario_values.items():
        model.constraints.append(Constraint(lhs=bound, sense=">=", rhs=expr, name=f"{name}:{scenario_name}"))
    return bound


def cvar(
    model,
    scenario_losses: Mapping[str, object],
    *,
    alpha: float,
    probabilities: Mapping[str, float] | None = None,
    name: str,
):
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be between 0 and 1.")
    threshold = model.add_variable(f"{name}_eta", lower_bound=-1_000_000.0, upper_bound=1_000_000.0)
    excess = model.var_array(f"{name}_excess", model.index_set(f"{name}_scenario", scenario_losses.keys()), lower_bound=0.0, upper_bound=1_000_000.0)
    probs = probabilities or {name: 1.0 / len(scenario_losses) for name in scenario_losses}
    for scenario_name, loss in scenario_losses.items():
        model.constraints.append(
            Constraint(lhs=excess[scenario_name], sense=">=", rhs=loss - threshold, name=f"{name}:{scenario_name}")
        )
    scale = 1.0 / max(1.0 - alpha, 1e-9)
    return threshold + scale * sum(probs[scenario_name] * excess[scenario_name] for scenario_name in scenario_losses)


def nonanticipativity(
    model,
    decisions: Mapping[str, Sequence[Variable]],
    *,
    groups: Sequence[Sequence[str]],
    name: str = "nonanticipativity",
) -> list[Constraint]:
    constraints: list[Constraint] = []
    for group_index, scenario_group in enumerate(groups):
        if len(scenario_group) < 2:
            continue
        anchor = decisions[scenario_group[0]]
        for scenario_name in scenario_group[1:]:
            candidate = decisions[scenario_name]
            if len(candidate) != len(anchor):
                raise ValueError("Nonanticipativity groups must compare equal-length decision vectors.")
            for var_index, (left, right) in enumerate(zip(anchor, candidate)):
                constraint = Constraint(lhs=left, sense="==", rhs=right, name=f"{name}:{group_index}:{scenario_name}:{var_index}")
                model.constraints.append(constraint)
                constraints.append(constraint)
    return constraints


def chance_constraint(
    model,
    scenario_constraints: Mapping[str, Constraint],
    *,
    max_violation_probability: float,
    probabilities: Mapping[str, float] | None = None,
    big_m: float = 1_000_000.0,
    name: str = "chance_constraint",
) -> list[Constraint]:
    if not 0.0 <= max_violation_probability <= 1.0:
        raise ValueError("max_violation_probability must be between 0 and 1.")
    selectors = model.var_array(f"{name}_violation", model.index_set(f"{name}_scenario", scenario_constraints.keys()), lower_bound=0.0, upper_bound=1.0, var_type=VarType.BINARY)
    probabilities = probabilities or {scenario_name: 1.0 / len(scenario_constraints) for scenario_name in scenario_constraints}
    constraints: list[Constraint] = []
    from polyhedron.modeling.transforms import indicator

    for scenario_name, constraint in scenario_constraints.items():
        constraints.extend(
            indicator(model, selectors[scenario_name], constraint, name=f"{name}:{scenario_name}", active_value=0, big_m=big_m)
        )
    aggregate = Constraint(
        lhs=sum(probabilities[scenario_name] * selectors[scenario_name] for scenario_name in scenario_constraints),
        sense="<=",
        rhs=float(max_violation_probability),
        name=f"{name}:budget",
    )
    model.constraints.append(aggregate)
    constraints.append(aggregate)
    return constraints


__all__ = [
    "ScenarioNode",
    "ScenarioTree",
    "ScenarioTreeBuilder",
    "worst_case",
    "cvar",
    "nonanticipativity",
    "chance_constraint",
]