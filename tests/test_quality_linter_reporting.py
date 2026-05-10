import json

import pytest

from polyhedron import Model
from polyhedron.modeling.element import Element
from polyhedron.quality import LintCategory, LintSeverity, lint_model


class RichLintElement(Element):
    x = Model.ContinuousVar(min=0)
    y = Model.ContinuousVar(min=0)
    z = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return self.x


class UnboundedObjectiveElement(Element):
    x = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return self.x


def _build_rich_model() -> Model:
    model = Model("lint-rich")
    elem = RichLintElement("e1")
    model.add_element(elem)

    @model.constraint(name="base")
    def base_constraint():
        return elem.x + elem.y <= 10

    @model.constraint(name="dominated")
    def dominated_constraint():
        return elem.x + elem.y <= 20

    @model.constraint(name="tiny")
    def tiny_constraint():
        return 1e-12 * elem.x + elem.z <= 1

    @model.constraint(name="big_m")
    def big_m_constraint():
        return 1_000_000 * Model.BinaryVar().create_variable("tmp_b") + elem.x <= 100

    return model


def test_report_renderers_and_semantic_fields() -> None:
    model = _build_rich_model()
    report = lint_model(
        model,
        dense_row_nnz_warn=1,
        tiny_coef_abs=1e-10,
        weak_bound_span_warn=10,
        numeric_range_warn_ratio=100,
        numeric_range_error_ratio=1e30,
    )

    assert report.summary.warning >= 1
    assert report.exit_code("error") in (0, 1)
    assert report.exit_code("warning") == 1

    json_payload = report.to_json()
    assert set(json_payload.keys()) == {"summary", "has_errors", "issues"}
    assert isinstance(json_payload["issues"], list)
    parsed = json.loads(report.to_json_str())
    assert parsed["summary"]["warning"] == report.summary.warning

    markdown = report.to_markdown()
    assert "## Model Lint Report" in markdown
    assert "| Severity | Code | Category | Message |" in markdown

    ansi = report.to_ansi(color="always")
    assert "\x1b[" in ansi
    assert "note: remediation:" in ansi

    for issue in report.issues:
        assert issue.category in set(LintCategory)
        assert issue.impact
        assert issue.remediation
        assert issue.evidence
        assert issue.tags


def test_exit_code_error_policy_with_unbounded_objective() -> None:
    model = Model("lint-error")
    model.objective_sense = "maximize"
    elem = UnboundedObjectiveElement("u1")
    model.add_element(elem)

    report = lint_model(model)

    assert any(issue.code == "LINT_OBJECTIVE_UNBOUNDED_RISK" for issue in report.issues)
    assert report.has_errors
    assert report.exit_code("error") == 1
    assert report.exit_code("warning") == 1
    assert report.exit_code("none") == 0


def test_numeric_range_rule_warn_and_error_thresholds() -> None:
    model_warn = Model("range-warn")
    e_warn = RichLintElement("w1")
    model_warn.add_element(e_warn)

    @model_warn.constraint(name="small")
    def small_coef():
        return e_warn.x <= 1

    @model_warn.constraint(name="large")
    def large_coef():
        return 1e8 * e_warn.y <= 1

    warn_report = lint_model(
        model_warn,
        numeric_range_warn_ratio=1e6,
        numeric_range_error_ratio=1e9,
    )
    warn_issue = next(issue for issue in warn_report.issues if issue.code == "LINT_NUMERIC_RANGE")
    assert warn_issue.severity == LintSeverity.WARNING

    model_error = Model("range-error")
    e_error = RichLintElement("e2")
    model_error.add_element(e_error)

    @model_error.constraint(name="small")
    def small_coef_error():
        return e_error.x <= 1

    @model_error.constraint(name="huge")
    def huge_coef_error():
        return 1e12 * e_error.y <= 1

    err_report = lint_model(
        model_error,
        numeric_range_warn_ratio=1e6,
        numeric_range_error_ratio=1e9,
    )
    err_issue = next(issue for issue in err_report.issues if issue.code == "LINT_NUMERIC_RANGE")
    assert err_issue.severity == LintSeverity.ERROR


def test_new_rules_positive_and_negative_controls() -> None:
    model = Model("rule-coverage")
    elem = RichLintElement("r1")
    model.add_element(elem)

    @model.constraint(name="dominant")
    def dominant():
        return elem.x + elem.y <= 10

    @model.constraint(name="dominated")
    def dominated():
        return elem.x + elem.y <= 20

    @model.constraint(name="tiny")
    def tiny():
        return 1e-12 * elem.x + elem.z <= 1

    @model.constraint(name="dense")
    def dense():
        return elem.x + elem.y + elem.z <= 100

    report = lint_model(
        model,
        dense_row_nnz_warn=2,
        tiny_coef_abs=1e-10,
        weak_bound_span_warn=50,
        numeric_range_warn_ratio=10,
        numeric_range_error_ratio=1e12,
    )
    codes = {issue.code for issue in report.issues}

    assert "LINT_DOMINATED_DUPLICATE" in codes
    assert "LINT_TINY_COEFFICIENT" in codes
    assert "LINT_ROW_DENSITY" in codes
    assert "LINT_WEAK_BOUNDS" in codes

    clean_report = lint_model(
        model,
        dense_row_nnz_warn=100,
        tiny_coef_abs=1e-20,
        weak_bound_span_warn=1e12,
        numeric_range_warn_ratio=1e20,
        numeric_range_error_ratio=1e21,
    )
    clean_codes = {issue.code for issue in clean_report.issues}
    assert "LINT_TINY_COEFFICIENT" not in clean_codes
    assert "LINT_ROW_DENSITY" not in clean_codes


def test_report_sorting_is_stable_by_severity_then_code() -> None:
    model = Model("sort-check")
    model.objective_sense = "maximize"
    elem = UnboundedObjectiveElement("s1")
    model.add_element(elem)

    report = lint_model(model)
    sorted_codes = [issue.code for issue in report.sorted_issues()]
    # Error-level unbounded objective should sort before warning-level findings.
    assert sorted_codes[0] == "LINT_OBJECTIVE_UNBOUNDED_RISK"


def test_exit_code_rejects_invalid_policy() -> None:
    model = Model("policy-check")
    elem = RichLintElement("p1")
    model.add_element(elem)

    report = lint_model(model)
    with pytest.raises(ValueError, match="fail_on"):
        report.exit_code("strict")
