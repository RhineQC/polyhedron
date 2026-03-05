from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Tuple

from polyhedron.core.scenario import ScenarioValues


@dataclass(frozen=True)
class Location:
    name: str
    x: float
    y: float


class DistanceMatrix:
    def __init__(self) -> None:
        self._distances: Dict[Tuple[str, str], float] = {}
        self._scenario_distances: Dict[Tuple[str, str], Dict[str, float]] = {}
        self._scenario_weights: Dict[str, float | None] = {}

    def add_scenario(self, name: str, weight: float | None = None) -> None:
        self._scenario_weights[name] = weight

    def set(self, a: Location, b: Location, distance: float) -> None:
        self._distances[(a.name, b.name)] = distance
        self._distances[(b.name, a.name)] = distance

    def set_scenarios(self, a: Location, b: Location, values: Mapping[str, float]) -> None:
        stored = {name: float(value) for name, value in values.items()}
        self._scenario_distances[(a.name, b.name)] = stored
        self._scenario_distances[(b.name, a.name)] = dict(stored)

    def get(self, a: Location, b: Location) -> float:
        if a.name == b.name:
            return 0.0
        return self._distances[(a.name, b.name)]

    def get_scenario(self, name: str, a: Location, b: Location) -> float:
        values = self._scenario_distances[(a.name, b.name)]
        return values[name]

    def get_scenario_values(self, a: Location, b: Location) -> ScenarioValues:
        values = self._scenario_distances[(a.name, b.name)]
        weights = self._resolve_weights(values)
        return ScenarioValues(values=values, weights=weights)

    def scenarios_for(self, a: Location, b: Location) -> Mapping[str, float]:
        return dict(self._scenario_distances[(a.name, b.name)])

    def _resolve_weights(self, values: Mapping[str, float]) -> Mapping[str, float] | None:
        if not self._scenario_weights:
            return None
        weights: Dict[str, float] = {}
        for name in values:
            weight = self._scenario_weights.get(name)
            if weight is None:
                return None
            weights[name] = float(weight)
        return weights
