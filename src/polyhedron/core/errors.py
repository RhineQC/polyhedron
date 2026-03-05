from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Iterable, List, Optional


class PolyhedronError(Exception):
    """Base error for Polyhedron with structured context."""

    def __init__(
        self,
        code: str,
        message: str,
        context: Optional[dict] = None,
        remediation: Optional[str] = None,
        origin: Optional[str] = None,
    ) -> None:
        self.code = code
        self.message = message
        self.context = context or {}
        self.remediation = remediation
        self.origin = origin
        super().__init__(self._format())

    def _format(self) -> str:
        parts = [f"{self.code}: {self.message}"]
        if self.origin:
            parts.append(f"origin={self.origin}")
        if self.context:
            parts.append(f"context={self.context}")
        if self.remediation:
            parts.append(f"how_to_fix={self.remediation}")
        return " | ".join(parts)


class ModelingError(PolyhedronError):
    """Invalid or unsupported model construction."""


class SolverError(PolyhedronError):
    """Solver or backend execution failure."""


class DataError(PolyhedronError):
    """Data ingestion or mapping failure."""


class QuboCompilationError(PolyhedronError):
    """QUBO compilation failure."""


class VisualizationError(PolyhedronError):
    """Visualization/rendering failure."""


class PerformanceError(PolyhedronError):
    """Performance/metrics failure."""


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    context: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context or {},
        }


def format_issues(issues: Iterable[ValidationIssue]) -> str:
    parts = []
    for issue in issues:
        context = f" context={issue.context}" if issue.context else ""
        parts.append(f"{issue.code}: {issue.message}{context}")
    return "; ".join(parts)


class ModelValidationError(PolyhedronError):
    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues: List[ValidationIssue] = list(issues)
        super().__init__(
            code="E_VALIDATION",
            message=format_issues(self.issues),
            context={"issues": [issue.to_dict() for issue in self.issues]},
            remediation="Fix model validation issues and re-run.",
            origin="polyhedron.core.validation",
        )

    def to_json(self, indent: int = 2) -> str:
        payload = {"issues": [issue.to_dict() for issue in self.issues]}
        return json.dumps(payload, indent=indent)
