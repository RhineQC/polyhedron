from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Dict, Optional


@dataclass
class ModelTimings:
    sections: Dict[str, float] = field(default_factory=dict)

    def add(self, name: str, duration: float) -> None:
        self.sections[name] = self.sections.get(name, 0.0) + duration

    def summary(self) -> str:
        lines = [f"{name}: {duration:.4f}s" for name, duration in self.sections.items()]
        return "\n".join(lines)


class TimingContext:
    def __init__(self, timings: ModelTimings, name: str):
        self.timings = timings
        self.name = name
        self._start: Optional[float] = None

    def __enter__(self):
        self._start = perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._start is None:
            return False
        self.timings.add(self.name, perf_counter() - self._start)
        return False


def timing(timings: ModelTimings, name: str) -> TimingContext:
    return TimingContext(timings, name)
