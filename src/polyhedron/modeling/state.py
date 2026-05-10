from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.modeling._helpers import AttrRef, finalize_constraint, get_attr, resolve_value
from polyhedron.modeling.element import Element


@dataclass(frozen=True)
class StateSeries:
    model: Model
    periods: Sequence[object]

    def add_to_model(self) -> "StateSeries":
        self.model.add_elements(period for period in self.periods if isinstance(period, Element))
        return self

    def transition(
        self,
        *,
        state_attr: AttrRef,
        initial_state=0.0,
        update=0.0,
        previous_weight: float = 1.0,
        name: str = "state_transition",
        tags: tuple[str, ...] = ("state", "transition"),
        group: str | None = None,
        source: str = "StateSeries.transition",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        constraints: list[Constraint] = []
        previous = initial_state
        for index, period in enumerate(self.periods):
            current = get_attr(period, state_attr)
            delta = resolve_value(update, period, index)
            constraint = current == previous_weight * previous + delta
            self.model.constraints.append(
                finalize_constraint(
                    constraint,
                    base_name=name,
                    index=index,
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={
                        "kind": "state_transition",
                        "stage_index": index,
                        **(metadata or {}),
                    },
                )
            )
            constraints.append(constraint)
            previous = current
        return constraints

    def balance(
        self,
        *,
        state_attr: AttrRef,
        initial_state=0.0,
        inflow_attr: AttrRef | None = None,
        outflow_attr: AttrRef | None = None,
        retention: float = 1.0,
        loss_attr: AttrRef | None = None,
        extra=0.0,
        name: str = "state_balance",
        tags: tuple[str, ...] = ("state", "balance"),
        group: str | None = None,
        source: str = "StateSeries.balance",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        def update(period: object, index: int):
            inflow = 0.0 if inflow_attr is None else get_attr(period, inflow_attr)
            outflow = 0.0 if outflow_attr is None else get_attr(period, outflow_attr)
            losses = 0.0 if loss_attr is None else get_attr(period, loss_attr)
            adjustment = resolve_value(extra, period, index)
            return inflow - outflow - losses + adjustment

        return self.transition(
            state_attr=state_attr,
            initial_state=initial_state,
            update=update,
            previous_weight=retention,
            name=name,
            tags=tags,
            group=group,
            source=source,
            metadata=metadata,
        )

    def link(
        self,
        *,
        current_attr: AttrRef,
        previous_attr: AttrRef,
        lag: int = 1,
        factor: float = 1.0,
        offset=0.0,
        name: str = "state_link",
        tags: tuple[str, ...] = ("state", "lag"),
        group: str | None = None,
        source: str = "StateSeries.link",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        if lag <= 0:
            raise ValueError("lag must be a positive integer.")
        constraints: list[Constraint] = []
        for index in range(lag, len(self.periods)):
            current = get_attr(self.periods[index], current_attr)
            previous = get_attr(self.periods[index - lag], previous_attr)
            constraint = current == factor * previous + resolve_value(offset, self.periods[index], index)
            self.model.constraints.append(
                finalize_constraint(
                    constraint,
                    base_name=name,
                    index=index,
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={
                        "kind": "state_link",
                        "lag": lag,
                        "stage_index": index,
                        **(metadata or {}),
                    },
                )
            )
            constraints.append(constraint)
        return constraints

    def terminal(
        self,
        *,
        state_attr: AttrRef,
        target,
        sense: str = "==",
        name: str = "terminal_state",
        tags: tuple[str, ...] = ("state", "terminal"),
        group: str | None = None,
        source: str = "StateSeries.terminal",
        metadata: dict[str, Any] | None = None,
    ) -> Constraint:
        if not self.periods:
            raise ValueError("StateSeries requires at least one period.")
        current = get_attr(self.periods[-1], state_attr)
        if sense == "==":
            constraint = current == target
        elif sense == ">=":
            constraint = current >= target
        elif sense == "<=":
            constraint = current <= target
        else:
            raise ValueError("sense must be one of '==', '>=', '<='.")
        self.model.constraints.append(
            finalize_constraint(
                constraint,
                base_name=name,
                tags=tags,
                group=group,
                source=source,
                metadata={"kind": "terminal_state", **(metadata or {})},
            )
        )
        return constraint

    def bounds(
        self,
        *,
        state_attr: AttrRef,
        lower=None,
        upper=None,
        name: str = "state_bound",
        tags: tuple[str, ...] = ("state", "bound"),
        group: str | None = None,
        source: str = "StateSeries.bounds",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        constraints: list[Constraint] = []
        for index, period in enumerate(self.periods):
            state = get_attr(period, state_attr)
            if lower is not None:
                lower_constraint = state >= resolve_value(lower, period, index)
                self.model.constraints.append(
                    finalize_constraint(
                        lower_constraint,
                        base_name=f"{name}_min",
                        index=index,
                        tags=tags,
                        group=group,
                        source=source,
                        metadata={"kind": "state_lower_bound", **(metadata or {})},
                    )
                )
                constraints.append(lower_constraint)
            if upper is not None:
                upper_constraint = state <= resolve_value(upper, period, index)
                self.model.constraints.append(
                    finalize_constraint(
                        upper_constraint,
                        base_name=f"{name}_max",
                        index=index,
                        tags=tags,
                        group=group,
                        source=source,
                        metadata={"kind": "state_upper_bound", **(metadata or {})},
                    )
                )
                constraints.append(upper_constraint)
        return constraints


__all__ = ["StateSeries"]