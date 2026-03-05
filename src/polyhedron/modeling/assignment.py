from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.solution import Solution, SolvedModel
from polyhedron.core.variable import Variable
from polyhedron.modeling.selection import SelectableElement


def _label(value: object) -> str:
    return str(getattr(value, "name", value))


def _group_key(value: object) -> object:
    try:
        hash(value)
        return value
    except TypeError:
        return id(value)


class AssignmentOption(SelectableElement):
    """Binary assignment decision between a subject and a target."""

    subject: object
    target: object
    cost: float

    def __init__(
        self,
        subject: object,
        target: object,
        *,
        cost: float = 0.0,
        name: Optional[str] = None,
        **kwargs,
    ):
        option_name = name or f"{_label(subject)}__{_label(target)}"
        self.subject = subject
        self.target = target
        self.cost = float(cost)
        super().__init__(option_name, subject=subject, target=target, cost=float(cost), **kwargs)

    def objective_contribution(self):
        return self.cost * self.selected


@dataclass(frozen=True)
class AssignmentGroup:
    model: "Model"
    options: Sequence[AssignmentOption]
    selector_attr: str = "selected"

    def add_to_model(self) -> "AssignmentGroup":
        self.model.add_elements(self.options)
        return self

    def selectors(self) -> list[Variable]:
        return [self._selector(option) for option in self.options]

    def total_cost(self):
        return sum((option.objective_contribution() for option in self.options), 0.0)

    def assign_exactly_one(self, *, name: str = "assign_exactly_one") -> list[Constraint]:
        constraints: list[Constraint] = []
        for _, group in self._group_by_subject():
            expression = sum((self._selector(option) for option in group), 0.0)
            constraints.append(self._add_constraint(expression == 1, f"{name}:{_label(group[0].subject)}"))
        return constraints

    def assign_at_least_one(self, *, name: str = "assign_at_least_one") -> list[Constraint]:
        constraints: list[Constraint] = []
        for _, group in self._group_by_subject():
            expression = sum((self._selector(option) for option in group), 0.0)
            constraints.append(self._add_constraint(expression >= 1, f"{name}:{_label(group[0].subject)}"))
        return constraints

    def assign_at_most_one_per_target(
        self,
        *,
        target_capacities: Optional[Mapping[object, int]] = None,
        default_capacity: int = 1,
        name: str = "target_capacity",
    ) -> list[Constraint]:
        constraints: list[Constraint] = []
        for key, group in self._group_by_target():
            capacity = default_capacity if target_capacities is None else int(target_capacities.get(key, default_capacity))
            expression = sum((self._selector(option) for option in group), 0.0)
            constraints.append(self._add_constraint(expression <= capacity, f"{name}:{_label(group[0].target)}"))
        return constraints

    def forbid(self, subject: object, target: object, *, name: str = "forbid_assignment") -> Constraint:
        for option in self.options:
            if option.subject == subject and option.target == target:
                return self._add_constraint(self._selector(option) == 0, name)
        raise ValueError("Assignment option not found for the given subject/target pair.")

    def selected_options(
        self,
        values: Mapping[Variable, float] | Solution | SolvedModel,
        *,
        threshold: float = 0.5,
    ) -> list[AssignmentOption]:
        if isinstance(values, SolvedModel):
            raw = values.values
        elif isinstance(values, Solution):
            raw = values.values
        else:
            raw = values
        return [
            option
            for option in self.options
            if float(raw.get(self._selector(option), 0.0)) >= threshold
        ]

    def _selector(self, option: AssignmentOption) -> Variable:
        value = getattr(option, self.selector_attr)
        if not isinstance(value, Variable):
            raise TypeError(f"Selector '{self.selector_attr}' must be a Variable.")
        return value

    def _group_by_subject(self) -> list[tuple[object, list[AssignmentOption]]]:
        groups: list[tuple[object, list[AssignmentOption]]] = []
        index: dict[object, int] = {}
        for option in self.options:
            key = _group_key(option.subject)
            if key not in index:
                index[key] = len(groups)
                groups.append((key, [option]))
            else:
                groups[index[key]][1].append(option)
        return groups

    def _group_by_target(self) -> list[tuple[object, list[AssignmentOption]]]:
        groups: list[tuple[object, list[AssignmentOption]]] = []
        index: dict[object, int] = {}
        for option in self.options:
            key = _group_key(option.target)
            if key not in index:
                index[key] = len(groups)
                groups.append((key, [option]))
            else:
                groups[index[key]][1].append(option)
        return groups

    def _add_constraint(self, constraint: Constraint, name: str) -> Constraint:
        constraint.name = name
        self.model.constraints.append(constraint)
        return constraint


__all__ = ["AssignmentOption", "AssignmentGroup"]
