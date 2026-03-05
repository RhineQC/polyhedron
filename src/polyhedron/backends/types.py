from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from polyhedron.core.variable import Variable


class SolveStatus(str, Enum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNBOUNDED = "unbounded"
    ERROR = "error"
    NOT_SOLVED = "not_solved"


@dataclass
class SolveSettings:
    time_limit: Optional[float] = None
    mip_gap: float = 0.01


@dataclass
class SolveResult:
    status: SolveStatus
    objective_value: Optional[float]
    values: Dict["Variable", float]
    solver_name: str
    message: Optional[str] = None


class CallbackRegistry(Protocol):
    on_solution: Optional[Callable[[SolveResult], None]]
    on_node: Optional[Callable[[object], None]]
