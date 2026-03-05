from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from polyhedron.core.expression import Expression
    from polyhedron.core.variable import Variable

Number = Union[int, float]
ConstraintOperand = Union["Expression", "Variable", Number]


@dataclass
class Constraint:
    lhs: ConstraintOperand
    sense: str
    rhs: ConstraintOperand
    name: Optional[str] = None
