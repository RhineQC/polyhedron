from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SolverContext:
    model: object
    depth: int = 0
    node_count: int = 0
    current_relaxation: Optional[object] = None
    incumbent_solution: Optional[object] = None
    solver: Optional[object] = None
