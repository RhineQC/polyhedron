from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.modeling.element import Element


AttrRef = str | Callable[[object], object]


def _get_attr(obj: object, ref: AttrRef):
    if callable(ref):
        return ref(obj)
    return getattr(obj, ref)


class InventoryBucket(Element):
    """Single time-bucket inventory state with bounded variables for backend portability."""

    inflow = Model.ContinuousVar(min=0.0, max=1_000_000.0)
    outflow = Model.ContinuousVar(min=0.0, max=1_000_000.0)
    level = Model.ContinuousVar(min=0.0, max=1_000_000.0)
    backlog = Model.ContinuousVar(min=0.0, max=1_000_000.0)

    backlog_penalty: float
    track_backlog: bool

    def __init__(
        self,
        name: str,
        *,
        backlog_penalty: float = 0.0,
        track_backlog: bool = False,
        **kwargs,
    ):
        self.backlog_penalty = float(backlog_penalty)
        self.track_backlog = track_backlog
        super().__init__(name, backlog_penalty=float(backlog_penalty), track_backlog=track_backlog, **kwargs)

    def objective_contribution(self):
        if self.track_backlog and self.backlog_penalty:
            return self.backlog_penalty * self.backlog
        return 0.0


@dataclass(frozen=True)
class InventorySeries:
    model: "Model"
    periods: Sequence[InventoryBucket]

    def add_to_model(self) -> "InventorySeries":
        self.model.add_elements(self.periods)
        return self

    def balance(self, initial_level: float = 0.0, *, name: str = "inventory_balance") -> list[Constraint]:
        constraints: list[Constraint] = []
        previous_level = initial_level
        for index, period in enumerate(self.periods):
            constraint = period.level == previous_level + period.inflow - period.outflow
            constraint.name = f"{name}:{index}"
            self.model.constraints.append(constraint)
            constraints.append(constraint)
            previous_level = period.level
        return constraints

    def meet_demand(
        self,
        demand,
        *,
        use_backlog: bool = False,
        name: str = "inventory_demand",
    ) -> list[Constraint]:
        constraints: list[Constraint] = []
        for index, period in enumerate(self.periods):
            required = self._demand_value(demand, period, index)
            lhs = period.outflow + period.backlog if use_backlog else period.outflow
            constraint = lhs >= required
            constraint.name = f"{name}:{index}"
            self.model.constraints.append(constraint)
            constraints.append(constraint)
        return constraints

    def capacity(self, limit, *, name: str = "inventory_capacity") -> list[Constraint]:
        constraints: list[Constraint] = []
        for index, period in enumerate(self.periods):
            bound = self._demand_value(limit, period, index)
            constraint = period.level <= bound
            constraint.name = f"{name}:{index}"
            self.model.constraints.append(constraint)
            constraints.append(constraint)
        return constraints

    def safety_stock(self, minimum, *, name: str = "inventory_safety_stock") -> list[Constraint]:
        constraints: list[Constraint] = []
        for index, period in enumerate(self.periods):
            bound = self._demand_value(minimum, period, index)
            constraint = period.level >= bound
            constraint.name = f"{name}:{index}"
            self.model.constraints.append(constraint)
            constraints.append(constraint)
        return constraints

    @staticmethod
    def _demand_value(source, period: InventoryBucket, index: int):
        if callable(source):
            return source(period, index)
        if isinstance(source, Sequence) and not isinstance(source, (str, bytes)):
            return source[index]
        if isinstance(source, str):
            return _get_attr(period, source)
        return source


__all__ = ["InventoryBucket", "InventorySeries"]
