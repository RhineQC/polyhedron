from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ScenarioValues:
    values: Mapping[str, float]
    weights: Mapping[str, float] | None = None

    def scenario_names(self) -> set[str]:
        return set(self.values)

    def value_for(self, name: str) -> float:
        return float(self.values[name])

    def expected_value(self) -> float:
        """Compute the expected value from scenario values and optional weights."""
        if not self.values:
            raise ValueError("ScenarioValues requires at least one scenario value.")

        if self.weights is None:
            total = float(len(self.values))
            return sum(float(value) for value in self.values.values()) / total

        missing = set(self.values) - set(self.weights)
        if missing:
            raise ValueError(f"Missing weights for scenarios: {sorted(missing)}")

        total_weight = sum(float(self.weights[name]) for name in self.values)
        if total_weight <= 0:
            raise ValueError("Scenario weights must sum to a positive value.")

        return sum(float(self.values[name]) * float(self.weights[name]) for name in self.values) / total_weight

    def __add__(self, other):
        from polyhedron.core.expression import Expression
        return Expression.from_scenario(self).__add__(other)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        from polyhedron.core.expression import Expression
        return Expression.from_scenario(self).__sub__(other)

    def __rsub__(self, other):
        from polyhedron.core.expression import Expression
        return Expression.from_scenario(self).__rsub__(other)

    def __neg__(self):
        from polyhedron.core.expression import Expression
        return -Expression.from_scenario(self)

    def __le__(self, other):
        from polyhedron.core.constraint import Constraint
        from polyhedron.core.expression import Expression
        return Constraint(lhs=Expression.from_scenario(self), sense="<=", rhs=other)

    def __ge__(self, other):
        from polyhedron.core.constraint import Constraint
        from polyhedron.core.expression import Expression
        return Constraint(lhs=Expression.from_scenario(self), sense=">=", rhs=other)

    def __eq__(self, other):  # type: ignore[override]
        from polyhedron.core.constraint import Constraint
        from polyhedron.core.expression import Expression
        return Constraint(lhs=Expression.from_scenario(self), sense="==", rhs=other)
