from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING

from polyhedron.backends.types import CallbackRegistry, SolveResult, SolveSettings
from polyhedron.core.errors import SolverError

if TYPE_CHECKING:
    from polyhedron.core.model import Model


class BackendError(SolverError):
    def __init__(
        self,
        message: str,
        *,
        context: Optional[dict] = None,
        remediation: Optional[str] = None,
        origin: Optional[str] = "polyhedron.backends",
    ) -> None:
        super().__init__(
            code="E_SOLVER_BACKEND",
            message=message,
            context=context,
            remediation=remediation,
            origin=origin,
        )


class SolverBackend(ABC):
    name: str

    @abstractmethod
    def solve(
        self,
        model: "Model",
        settings: SolveSettings,
        callbacks: Optional[CallbackRegistry],
    ) -> SolveResult:
        raise NotImplementedError
