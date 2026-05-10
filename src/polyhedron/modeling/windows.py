from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.modeling._helpers import AttrRef, finalize_constraint, get_attr, resolve_value
from polyhedron.modeling.element import Element


@dataclass(frozen=True)
class WindowSeries:
    model: Model
    periods: Sequence[object]

    def add_to_model(self) -> "WindowSeries":
        self.model.add_elements(period for period in self.periods if isinstance(period, Element))
        return self

    def lag_link(
        self,
        *,
        current_attr: AttrRef,
        previous_attr: AttrRef,
        lag: int = 1,
        factor: float = 1.0,
        offset=0.0,
        name: str = "lag_link",
        tags: tuple[str, ...] = ("window", "lag"),
        group: str | None = None,
        source: str = "WindowSeries.lag_link",
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
                    metadata={"kind": "lag_link", "lag": lag, **(metadata or {})},
                )
            )
            constraints.append(constraint)
        return constraints

    def rolling_sum(
        self,
        *,
        attr: AttrRef,
        window: int,
        upper=None,
        lower=None,
        equal=None,
        name: str = "rolling_sum",
        tags: tuple[str, ...] = ("window", "rolling_sum"),
        group: str | None = None,
        source: str = "WindowSeries.rolling_sum",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        if window <= 0:
            raise ValueError("window must be a positive integer.")
        constraints: list[Constraint] = []
        for end in range(window - 1, len(self.periods)):
            start = end - window + 1
            total = sum(get_attr(self.periods[position], attr) for position in range(start, end + 1))
            bound_metadata = {
                "kind": "rolling_sum",
                "window": window,
                "start": start,
                "end": end,
                **(metadata or {}),
            }
            if upper is not None:
                upper_constraint = total <= resolve_value(upper, self.periods[end], end)
                self.model.constraints.append(
                    finalize_constraint(
                        upper_constraint,
                        base_name=f"{name}_max",
                        index=end,
                        tags=tags,
                        group=group,
                        source=source,
                        metadata=bound_metadata | {"sense": "<="},
                    )
                )
                constraints.append(upper_constraint)
            if lower is not None:
                lower_constraint = total >= resolve_value(lower, self.periods[end], end)
                self.model.constraints.append(
                    finalize_constraint(
                        lower_constraint,
                        base_name=f"{name}_min",
                        index=end,
                        tags=tags,
                        group=group,
                        source=source,
                        metadata=bound_metadata | {"sense": ">="},
                    )
                )
                constraints.append(lower_constraint)
            if equal is not None:
                equality = total == resolve_value(equal, self.periods[end], end)
                self.model.constraints.append(
                    finalize_constraint(
                        equality,
                        base_name=f"{name}_eq",
                        index=end,
                        tags=tags,
                        group=group,
                        source=source,
                        metadata=bound_metadata | {"sense": "=="},
                    )
                )
                constraints.append(equality)
        return constraints

    def ramp(
        self,
        *,
        attr: AttrRef,
        up=None,
        down=None,
        name: str = "ramp",
        tags: tuple[str, ...] = ("window", "ramp"),
        group: str | None = None,
        source: str = "WindowSeries.ramp",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        constraints: list[Constraint] = []
        for index in range(1, len(self.periods)):
            current = get_attr(self.periods[index], attr)
            previous = get_attr(self.periods[index - 1], attr)
            if up is not None:
                up_constraint = current - previous <= resolve_value(up, self.periods[index], index)
                self.model.constraints.append(
                    finalize_constraint(
                        up_constraint,
                        base_name=f"{name}_up",
                        index=index,
                        tags=tags,
                        group=group,
                        source=source,
                        metadata={"kind": "ramp_up", **(metadata or {})},
                    )
                )
                constraints.append(up_constraint)
            if down is not None:
                down_constraint = previous - current <= resolve_value(down, self.periods[index], index)
                self.model.constraints.append(
                    finalize_constraint(
                        down_constraint,
                        base_name=f"{name}_down",
                        index=index,
                        tags=tags,
                        group=group,
                        source=source,
                        metadata={"kind": "ramp_down", **(metadata or {})},
                    )
                )
                constraints.append(down_constraint)
        return constraints

    def min_active_run(
        self,
        *,
        attr: AttrRef,
        minimum: int,
        initial_active: float = 0.0,
        name: str = "min_active_run",
        tags: tuple[str, ...] = ("window", "minimum_run"),
        group: str | None = None,
        source: str = "WindowSeries.min_active_run",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        if minimum <= 0:
            raise ValueError("minimum must be a positive integer.")
        constraints: list[Constraint] = []
        total_periods = len(self.periods)
        for index, period in enumerate(self.periods):
            current = get_attr(period, attr)
            previous = initial_active if index == 0 else get_attr(self.periods[index - 1], attr)
            start = current - previous
            if index + minimum <= total_periods:
                window_sum = sum(get_attr(self.periods[position], attr) for position in range(index, index + minimum))
                constraint = window_sum >= minimum * start
            else:
                constraint = current <= previous
            self.model.constraints.append(
                finalize_constraint(
                    constraint,
                    base_name=name,
                    index=index,
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={"kind": "minimum_run", "minimum": minimum, **(metadata or {})},
                )
            )
            constraints.append(constraint)
        return constraints

    def max_active_run(
        self,
        *,
        attr: AttrRef,
        maximum: int,
        name: str = "max_active_run",
        tags: tuple[str, ...] = ("window", "maximum_run"),
        group: str | None = None,
        source: str = "WindowSeries.max_active_run",
        metadata: dict[str, Any] | None = None,
    ) -> list[Constraint]:
        if maximum <= 0:
            raise ValueError("maximum must be a positive integer.")
        constraints: list[Constraint] = []
        if len(self.periods) <= maximum:
            return constraints
        for end in range(maximum, len(self.periods)):
            start = end - maximum
            total = sum(get_attr(self.periods[position], attr) for position in range(start, end + 1))
            constraint = total <= maximum
            self.model.constraints.append(
                finalize_constraint(
                    constraint,
                    base_name=name,
                    index=end,
                    tags=tags,
                    group=group,
                    source=source,
                    metadata={
                        "kind": "maximum_run",
                        "maximum": maximum,
                        "start": start,
                        "end": end,
                        **(metadata or {}),
                    },
                )
            )
            constraints.append(constraint)
        return constraints


__all__ = ["WindowSeries"]