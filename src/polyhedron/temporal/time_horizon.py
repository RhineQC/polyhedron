from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class TimeHorizon:
    periods: int
    step: str = "1h"
    start: Optional["pd.Timestamp"] = None

    def __post_init__(self) -> None:
        if self.periods <= 0:
            raise ValueError("TimeHorizon.periods must be positive.")

    def __iter__(self) -> Iterator[int]:
        return iter(range(self.periods))

    def __len__(self) -> int:
        return self.periods
