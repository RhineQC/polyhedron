import json

from polyhedron.core.errors import (
    DataError,
    ModelValidationError,
    PerformanceError,
    PolyhedronError,
    QuboCompilationError,
    SolverError,
    ValidationIssue,
    VisualizationError,
    format_issues,
)


def test_polyhedron_error_format_includes_optional_parts() -> None:
    err = PolyhedronError(
        code="E_TEST",
        message="boom",
        context={"x": 1},
        remediation="do thing",
        origin="tests",
    )

    text = str(err)
    assert "E_TEST: boom" in text
    assert "origin=tests" in text
    assert "context={'x': 1}" in text
    assert "how_to_fix=do thing" in text


def test_polyhedron_error_format_without_optional_parts() -> None:
    err = PolyhedronError(code="E_MIN", message="minimal")
    assert str(err) == "E_MIN: minimal"


def test_validation_issue_to_dict_and_format_issues() -> None:
    a = ValidationIssue(code="A", message="m1", context={"k": "v"})
    b = ValidationIssue(code="B", message="m2")

    assert a.to_dict() == {"code": "A", "message": "m1", "context": {"k": "v"}}
    assert b.to_dict() == {"code": "B", "message": "m2", "context": {}}

    text = format_issues([a, b])
    assert "A: m1 context={'k': 'v'}" in text
    assert "B: m2" in text


def test_model_validation_error_serialization() -> None:
    issues = [ValidationIssue(code="E1", message="bad value", context={"field": "x"})]
    err = ModelValidationError(issues)

    assert err.code == "E_VALIDATION"
    assert "E1: bad value" in err.message
    payload = json.loads(err.to_json(indent=2))
    assert payload["issues"][0]["code"] == "E1"
    assert payload["issues"][0]["context"] == {"field": "x"}


def test_specific_error_types_are_polyhedron_errors() -> None:
    for cls in [
        DataError,
        SolverError,
        QuboCompilationError,
        VisualizationError,
        PerformanceError,
    ]:
        err = cls(code="E", message="m")
        assert isinstance(err, PolyhedronError)
