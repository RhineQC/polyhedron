from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from polyhedron.core.expression import Expression, QuadraticExpression
    from polyhedron.core.variable import Variable

Number = Union[int, float]
ConstraintOperand = Union["Expression", "QuadraticExpression", "Variable", Number]


@dataclass(eq=False)
class Constraint:
    lhs: ConstraintOperand
    sense: str
    rhs: ConstraintOperand
    name: Optional[str] = None
    tags: tuple[str, ...] = ()
    index_key: Any = None
    group: Optional[str] = None
    source: Optional[str] = None
    unit: Optional[str] = None
    relaxable: bool = False
    metadata: Optional[dict[str, Any]] = None
