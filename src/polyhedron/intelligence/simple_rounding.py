from __future__ import annotations

from typing import Dict, Optional

from polyhedron.core.variable import Variable
from polyhedron.intelligence.context import SolverContext
from polyhedron.intelligence.heuristics import Frequency, HeuristicBase, Priority


class SimpleRoundingHeuristic(HeuristicBase):
    def __init__(self, threshold: float = 0.5, **kwargs) -> None:
        super().__init__(
            name="simple_rounding",
            priority=Priority.LOW,
            frequency=Frequency.SOLUTION,
            **kwargs,
        )
        self.threshold = threshold

    def apply(self, context: SolverContext) -> Optional[Dict[Variable, float]]:
        relaxation = context.current_relaxation
        if relaxation is None or not hasattr(relaxation, "value"):
            return None

        solution: Dict[Variable, float] = {}
        for var in getattr(relaxation, "fractional_vars", []):
            val = relaxation.value(var)
            solution[var] = 1.0 if val >= self.threshold else 0.0
        return solution if solution else None
