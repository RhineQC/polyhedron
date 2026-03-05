from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Dict, Optional

from polyhedron.intelligence.context import SolverContext


class Frequency(Enum):
    ROOT = "root"
    NODE = "node"
    PERIODIC = "periodic"
    SOLUTION = "solution"
    ADAPTIVE = "adaptive"


class Priority(Enum):
    CRITICAL = 100
    HIGH = 75
    MEDIUM = 50
    LOW = 25
    MINIMAL = 10


@dataclass
class HeuristicStats:
    calls: int = 0
    solutions_found: int = 0
    time_spent: float = 0.0


class HeuristicBase(ABC):
    def __init__(
        self,
        name: str,
        priority: Priority = Priority.MEDIUM,
        frequency: Frequency = Frequency.NODE,
        max_depth: Optional[int] = None,
        enabled: bool = True,
    ):
        self.name = name
        self.priority = priority
        self.frequency = frequency
        self.max_depth = max_depth
        self.enabled = enabled
        self.stats = HeuristicStats()

    def should_apply(self, context) -> bool:
        if not self.enabled:
            return False
        if self.max_depth is not None and getattr(context, "depth", 0) > self.max_depth:
            return False
        return True

    def run(self, context: SolverContext) -> Optional[Dict[object, float]]:
        start = perf_counter()
        self.stats.calls += 1
        try:
            result = self.apply(context)
        finally:
            self.stats.time_spent += perf_counter() - start
        if result:
            self.stats.solutions_found += 1
        return result

    @abstractmethod
    def apply(self, context: SolverContext) -> Optional[Dict[object, float]]:
        raise NotImplementedError
