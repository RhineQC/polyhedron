from polyhedron import Model
from polyhedron.modeling.element import Element
from polyhedron.units import validate_model_units


class UnitElement(Element):
    power = Model.ContinuousVar(min=0.0, unit="MW")
    cost = Model.ContinuousVar(min=0.0, unit="EUR")

    def objective_contribution(self):
        return 0


def test_units_validation_flags_mismatched_dimensions() -> None:
    model = Model("units-demo")
    elem = UnitElement("u1")
    model.add_element(elem)

    @model.constraint(name="bad_units")
    def bad_units():
        return elem.power == elem.cost

    report = validate_model_units(model)
    assert not report.is_valid
    assert any(issue.code == "UNIT_CONSTRAINT_MISMATCH" for issue in report.issues)
