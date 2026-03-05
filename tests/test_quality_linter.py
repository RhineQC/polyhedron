from polyhedron import Model
from polyhedron.modeling.element import Element
from polyhedron.quality import LintSeverity, lint_model


class BigMElement(Element):
    x = Model.ContinuousVar(min=0.0)
    b = Model.BinaryVar()

    def objective_contribution(self):
        return 0


def test_linter_detects_big_m_and_unbound_variable() -> None:
    model = Model("lint-demo")
    elem = BigMElement("e1")
    model.add_element(elem)

    @model.constraint(name="big_m")
    def big_m_constraint():
        return elem.x <= 1_000_000 * elem.b

    report = lint_model(model, big_m_threshold=1e5)
    codes = {issue.code for issue in report.issues}

    assert "LINT_BIG_M" in codes
    assert any(issue.severity == LintSeverity.WARNING for issue in report.issues)
