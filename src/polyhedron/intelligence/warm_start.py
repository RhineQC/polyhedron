from __future__ import annotations

from typing import Dict, Optional

from polyhedron.intelligence.heuristics import Frequency, HeuristicBase, Priority
from polyhedron.intelligence.context import SolverContext


class WarmStart(HeuristicBase):
    def __init__(
        self,
        solution: Optional[Dict] = None,
        source: Optional[str] = None,
        quality: float = 1.0,
        **kwargs,
    ):
        super().__init__(
            name="WarmStart",
            priority=Priority.CRITICAL,
            frequency=Frequency.ROOT,
            **kwargs,
        )
        self.solution = solution
        self.source = source
        self.quality = quality

    def apply(self, context: SolverContext):
        if context.solver is not None:
            context.solver.set_warm_start(self.solution, self.quality)
