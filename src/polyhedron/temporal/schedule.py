from __future__ import annotations

from typing import Iterable, List
import warnings

from polyhedron.core.variable import Variable
from polyhedron.modeling.element import Element
from polyhedron.temporal.time_horizon import TimeHorizon


class Schedule:
    def __init__(self, elements: List[Element], horizon: TimeHorizon):
        if not elements:
            warnings.warn("Schedule initialized with no elements.", RuntimeWarning)
            self.elements = []
            self.horizon = horizon
            self._schedule = []
            return
        self.elements = elements
        self.horizon = horizon
        self._schedule: List[List[Element]] = []

        for element in elements:
            temporal_series: List[Element] = []
            for t in range(horizon.periods):
                init_kwargs = {
                    k: v
                    for k, v in element.__dict__.items()
                    if not k.startswith("_")
                    and k != "name"
                    and not isinstance(v, Variable)
                }
                element_copy = element.__class__(
                    name=f"{element.name}_t{t}",
                    **init_kwargs,
                )
                temporal_series.append(element_copy)
            self._schedule.append(temporal_series)

    def __getitem__(self, index: int) -> List[Element]:
        return self._schedule[index]

    def __iter__(self) -> Iterable[List[Element]]:
        return iter(self._schedule)

    def __len__(self) -> int:
        return len(self._schedule)
