from polyhedron import Model
from polyhedron.modeling.element import Element
from polyhedron.quality import debug_infeasibility


class BoundElement(Element):
    x = Model.ContinuousVar(min=0.0, max=10.0)

    def objective_contribution(self):
        return 0


def test_infeasibility_debugger_detects_bound_conflict() -> None:
    model = Model("infeasible-debug")
    elem = BoundElement("e1")
    model.add_element(elem)

    @model.constraint(name="upper")
    def upper():
        return elem.x <= 1

    @model.constraint(name="lower")
    def lower():
        return elem.x >= 2

    report = debug_infeasibility(model)
    assert any(s.kind == "bound_conflict" for s in report.suspects)


def test_infeasibility_debugger_groups_violations() -> None:
    model = Model("infeasible-group-debug")
    elem = BoundElement("e2")
    model.add_element(elem)

    @model.constraint(name="capacity:0")
    def cap_0():
        return elem.x <= 1

    @model.constraint(name="capacity:1")
    def cap_1():
        return elem.x <= 1

    report = debug_infeasibility(model, {elem.x: 5.0})
    assert report.violated_constraints
    assert report.violated_groups
    assert report.violated_groups[0][0] == "capacity"
