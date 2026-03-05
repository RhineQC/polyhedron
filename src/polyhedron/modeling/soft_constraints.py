from __future__ import annotations

from dataclasses import dataclass, field

from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.modeling.element import Element


class _SoftSlack(Element):
    violation = Model.ContinuousVar(min=0.0, max=1_000_000.0)
    weight: float

    def __init__(self, name: str, weight: float, *, max_violation: float):
        self.weight = float(weight)
        self.max_violation = float(max_violation)
        super().__init__(name, weight=float(weight), max_violation=float(max_violation))
        self.violation = type(self.violation)(
            name=self.violation.name,
            var_type=self.violation.var_type,
            lower_bound=self.violation.lower_bound,
            upper_bound=float(max_violation),
            value=self.violation.value,
        )
        self._variables["violation"] = self.violation

    def objective_contribution(self):
        return self.weight * self.violation


class _SoftEqualitySlack(Element):
    under = Model.ContinuousVar(min=0.0, max=1_000_000.0)
    over = Model.ContinuousVar(min=0.0, max=1_000_000.0)
    weight: float

    def __init__(self, name: str, weight: float, *, max_violation: float):
        self.weight = float(weight)
        self.max_violation = float(max_violation)
        super().__init__(name, weight=float(weight), max_violation=float(max_violation))
        self.under = type(self.under)(
            name=self.under.name,
            var_type=self.under.var_type,
            lower_bound=self.under.lower_bound,
            upper_bound=float(max_violation),
            value=self.under.value,
        )
        self.over = type(self.over)(
            name=self.over.name,
            var_type=self.over.var_type,
            lower_bound=self.over.lower_bound,
            upper_bound=float(max_violation),
            value=self.over.value,
        )
        self._variables["under"] = self.under
        self._variables["over"] = self.over

    def objective_contribution(self):
        return self.weight * self.under + self.weight * self.over


@dataclass
class SoftConstraint:
    """Relax a hard constraint by adding bounded non-negative slack penalties."""

    model: "Model"
    constraint: Constraint
    weight: float
    name: str = "soft_constraint"
    max_violation: float = 1_000_000.0
    penalty_elements: list[Element] = field(default_factory=list, init=False)
    relaxed_constraint: Constraint | None = field(default=None, init=False)

    def add_to_model(self) -> Constraint:
        if self.max_violation <= 0:
            raise ValueError("max_violation must be positive.")

        if self.constraint.sense == "<=":
            slack = _SoftSlack(f"{self.name}_slack", self.weight, max_violation=self.max_violation)
            self.model.add_element(slack)
            relaxed = Constraint(
                lhs=self.constraint.lhs,
                sense="<=",
                rhs=self.constraint.rhs + slack.violation,
                name=self.name,
            )
            self.penalty_elements = [slack]
        elif self.constraint.sense == ">=":
            slack = _SoftSlack(f"{self.name}_slack", self.weight, max_violation=self.max_violation)
            self.model.add_element(slack)
            relaxed = Constraint(
                lhs=self.constraint.lhs,
                sense=">=",
                rhs=self.constraint.rhs - slack.violation,
                name=self.name,
            )
            self.penalty_elements = [slack]
        elif self.constraint.sense == "==":
            slack = _SoftEqualitySlack(
                f"{self.name}_slack",
                self.weight,
                max_violation=self.max_violation,
            )
            self.model.add_element(slack)
            relaxed = Constraint(
                lhs=self.constraint.lhs,
                sense="==",
                rhs=self.constraint.rhs + slack.under - slack.over,
                name=self.name,
            )
            self.penalty_elements = [slack]
        else:
            raise ValueError(f"Unsupported constraint sense: {self.constraint.sense}")

        self.model.constraints.append(relaxed)
        self.relaxed_constraint = relaxed
        return relaxed


def soften_constraint(
    model: "Model",
    constraint: Constraint,
    *,
    weight: float,
    name: str = "soft_constraint",
    max_violation: float = 1_000_000.0,
) -> SoftConstraint:
    soft = SoftConstraint(
        model=model,
        constraint=constraint,
        weight=weight,
        name=name,
        max_violation=max_violation,
    )
    soft.add_to_model()
    return soft


__all__ = ["SoftConstraint", "soften_constraint"]
