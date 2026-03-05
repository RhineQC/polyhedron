from polyhedron import Model
from polyhedron.modeling.element import Element
from polyhedron.quality import explain_model


class ExplainElement(Element):
    x = Model.ContinuousVar(min=0.0)
    y = Model.ContinuousVar(min=0.0)

    def objective_contribution(self):
        return self.x + self.y


def test_explainability_report_contains_model_shape() -> None:
    model = Model("explain")
    elem = ExplainElement("e1")
    model.add_element(elem)

    @model.constraint(name="cap")
    def cap():
        return elem.x + elem.y <= 10

    report = explain_model(model)
    assert report.size.variables_total == 2
    assert report.size.constraints_total == 1
    assert report.constraints.max_terms >= 1
    assert "Model Explainability Report" in report.to_markdown()
