from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class BranchingStrategy:
    rule: str
    priorities: Dict[str, int]

    def apply(self, model, variables: List[object]) -> None:
        for var in variables:
            if hasattr(var, "name"):
                for key, priority in self.priorities.items():
                    if key in var.name:
                        try:
                            object.__setattr__(var, "_branching_priority", priority)
                        except AttributeError:
                            setattr(var, "_branching_priority", priority)
