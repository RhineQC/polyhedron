from polyhedron import Element, Model
from polyhedron.modeling import ScenarioTree, add_sos1


class BaseElement(Element):
    x = Model.ContinuousVar(min=0, max=10)
    y = Model.ContinuousVar(min=0, max=10)
    z = Model.BinaryVar()

    def objective_contribution(self):
        return self.x + self.y


def test_abs_min_max_piecewise_indicator_and_sos_helpers() -> None:
    model = Model("transforms")
    elem = BaseElement("e1")
    model.add_element(elem)

    absolute = model.abs_var(elem.x - 3, name="abs_dev", upper_bound=10)
    maximum = model.max_var([elem.x, elem.y + 1], name="peak")
    minimum = model.min_var([elem.x, elem.y + 1], name="floor")
    pw = model.piecewise_linear(name="tariff", input_var=elem.x, breakpoints=[0, 5, 10], values=[0, 4, 9])
    indicator_constraints = model.indicator(elem.z, elem.x + elem.y <= 7, name="switch")
    sos_constraints = add_sos1(model, [elem.x, elem.y], name="only_one")

    assert absolute.name == "abs_dev"
    assert maximum.name == "peak"
    assert minimum.name == "floor"
    assert pw.output.name == "tariff"
    assert len(indicator_constraints) == 1
    assert len(sos_constraints) == 5


def test_uncertainty_and_risk_helpers_add_constraints() -> None:
    model = Model("uncertainty")
    elem = BaseElement("e1")
    model.add_element(elem)

    tree = ScenarioTree(nodes=())
    assert tree.leaves() == ()

    worst = model.worst_case({"base": elem.x, "stress": elem.y + 2}, name="wc")
    cvar_expr = model.cvar({"base": elem.x, "stress": elem.y + 4}, alpha=0.9, name="risk")
    nonant = model.nonanticipativity(
        {"s1": [elem.x], "s2": [elem.y]},
        groups=[["s1", "s2"]],
    )
    chance = model.chance_constraint(
        {
            "base": elem.x <= 5,
            "stress": elem.y <= 6,
        },
        max_violation_probability=0.5,
        name="chance",
    )

    assert worst.name == "wc"
    assert nonant[0].name.startswith("nonanticipativity")
    assert chance[-1].name == "chance:budget"
    assert cvar_expr.terms or getattr(cvar_expr, "linear_terms", None) is not None