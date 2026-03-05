from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.solution import Solution, SolvedModel
from polyhedron.core.variable import Variable
from polyhedron.modeling.element import Element
from polyhedron.core.model import Model


class SelectableElement(Element):
    """Base element that exposes a binary selection variable."""

    selected = Model.BinaryVar()

    def objective_contribution(self):
        return 0.0


@dataclass(frozen=True)
class SelectionGroup:
    model: Model
    elements: Sequence[SelectableElement]
    selector_attr: str = "selected"

    def add_to_model(self) -> "SelectionGroup":
        self.model.add_elements(self.elements)
        return self

    def selectors(self) -> list[Variable]:
        return [self._selector(elem) for elem in self.elements]

    def sum_selected(self, elements: Optional[Iterable[SelectableElement]] = None):
        items = list(elements) if elements is not None else list(self.elements)
        return sum((self._selector(elem) for elem in items), 0.0)

    def weighted_sum(
        self,
        *,
        weight_attr: Optional[str] = None,
        weights: Optional[Mapping[SelectableElement, float]] = None,
        elements: Optional[Iterable[SelectableElement]] = None,
    ):
        items = list(elements) if elements is not None else list(self.elements)
        terms = []
        for elem in items:
            if weights is not None:
                weight = float(weights.get(elem, 0.0))
            elif weight_attr is not None:
                weight = float(getattr(elem, weight_attr))
            else:
                raise ValueError("weight_attr or weights must be provided.")
            terms.append(weight * self._selector(elem))
        return sum(terms, 0.0)

    def choose_exactly(self, k: int, *, name: str = "select_exactly") -> Constraint:
        return self._add_constraint(self.sum_selected() == k, name)

    def choose_at_least(self, k: int, *, name: str = "select_at_least") -> Constraint:
        return self._add_constraint(self.sum_selected() >= k, name)

    def choose_at_most(self, k: int, *, name: str = "select_at_most") -> Constraint:
        return self._add_constraint(self.sum_selected() <= k, name)

    def mutually_exclusive(
        self,
        *elements: SelectableElement,
        name: str = "mutually_exclusive",
    ) -> Constraint:
        return self._add_constraint(self.sum_selected(elements) <= 1, name)

    def dependency(
        self,
        required: SelectableElement,
        dependent: SelectableElement,
        *,
        name: str = "dependency",
    ) -> Constraint:
        return self._add_constraint(self._selector(dependent) <= self._selector(required), name)

    def budget_limit(
        self,
        limit: float,
        *,
        weight_attr: str = "cost",
        weights: Optional[Mapping[SelectableElement, float]] = None,
        name: str = "budget_limit",
    ) -> Constraint:
        expr = self.weighted_sum(weight_attr=weight_attr, weights=weights)
        return self._add_constraint(expr <= float(limit), name)

    def selected_elements(
        self,
        values: Mapping[Variable, float] | Solution | SolvedModel,
        *,
        threshold: float = 0.5,
    ) -> list[SelectableElement]:
        if isinstance(values, SolvedModel):
            raw = values.values
        elif isinstance(values, Solution):
            raw = values.values
        else:
            raw = values
        selected: list[SelectableElement] = []
        for elem in self.elements:
            var = self._selector(elem)
            if float(raw.get(var, 0.0)) >= threshold:
                selected.append(elem)
        return selected

    def _selector(self, element: SelectableElement) -> Variable:
        value = getattr(element, self.selector_attr)
        if not isinstance(value, Variable):
            raise TypeError(f"Selector '{self.selector_attr}' must be a Variable.")
        return value

    def _add_constraint(self, constraint: Constraint, name: str) -> Constraint:
        constraint.name = name
        self.model.constraints.append(constraint)
        return constraint


__all__ = ["SelectableElement", "SelectionGroup"]
