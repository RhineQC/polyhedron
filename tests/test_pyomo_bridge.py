import pytest

from polyhedron import Model, maximize, minimize
from polyhedron.backends.compiler import compile_model
from polyhedron.bridges import (
    apply_pyomo_values_to_polyhedron,
    apply_polyhedron_values_to_pyomo,
    convert_polyhedron_model,
    convert_pyomo_model,
)
from polyhedron.modeling.element import Element

pytestmark = pytest.mark.bridge


pyomo = pytest.importorskip("pyomo.environ")


class BridgeElement(Element):
    x = Model.ContinuousVar(min=0, max=10)
    y = Model.BinaryVar()

    def objective_contribution(self):
        return 2 * self.x + 3 * self.y


class MultiObjectiveBridgeElement(Element):
    x = Model.ContinuousVar(min=0, max=10)
    y = Model.ContinuousVar(min=0, max=10)

    @minimize(name="cost", weight=2.0)
    def cost(self):
        return self.x + self.y

    @maximize(name="service", weight=0.5)
    def service(self):
        return self.y


def _build_poly_model() -> tuple[Model, BridgeElement]:
    model = Model("poly-bridge")
    elem = BridgeElement("e1")
    model.add_element(elem)

    @model.constraint(name="c1")
    def c1():
        return elem.x <= 5 + 10 * elem.y

    @model.constraint(name="c2")
    def c2():
        return elem.x >= 1

    return model, elem


def test_pyomo_to_polyhedron_conversion_linear_model() -> None:
    m = pyomo.ConcreteModel()
    m.x = pyomo.Var(bounds=(0, 10))
    m.y = pyomo.Var(domain=pyomo.Binary)

    m.c1 = pyomo.Constraint(expr=m.x <= 5 + 10 * m.y)
    m.c2 = pyomo.Constraint(expr=pyomo.inequality(1, m.x, 9))
    m.obj = pyomo.Objective(expr=2 * m.x + 3 * m.y, sense=pyomo.minimize)

    conversion = convert_pyomo_model(m, model_name="converted")

    assert conversion.model.name == "converted"
    assert "x" in conversion.polyhedron_variables
    assert "y" in conversion.polyhedron_variables

    compiled = compile_model(conversion.model)
    assert len(compiled.variables) == 2
    assert len(compiled.constraints) == 3  # c1 ub + c2 lb + c2 ub
    assert compiled.objective_sense == "minimize"
    assert {cons.name for cons in compiled.constraints} == {"c1:ub", "c2:lb", "c2:ub"}


def test_polyhedron_to_pyomo_conversion_linear_model() -> None:
    model, _elem = _build_poly_model()

    conversion = convert_polyhedron_model(model)
    py_model = conversion.pyomo_model

    vars_count = len(list(py_model.component_data_objects(pyomo.Var, active=True)))
    cons_count = len(list(py_model.component_data_objects(pyomo.Constraint, active=True)))
    obj_count = len(list(py_model.component_data_objects(pyomo.Objective, active=True)))

    assert vars_count == 2
    assert cons_count == 2
    assert obj_count == 1


def test_polyhedron_multi_objective_exports_as_single_weighted_pyomo_objective() -> None:
    model = Model("poly-multi-bridge")
    elem = MultiObjectiveBridgeElement("e1")
    model.add_element(elem)

    conversion = convert_polyhedron_model(model)
    objectives = list(conversion.pyomo_model.component_data_objects(pyomo.Objective, active=True))

    assert len(objectives) == 1

    conversion.pyomo_variables[elem.x.name].set_value(3.0)
    conversion.pyomo_variables[elem.y.name].set_value(4.0)
    assert pytest.approx(pyomo.value(objectives[0].expr), rel=1e-9) == 12.0


def test_roundtrip_value_transfer_between_polyhedron_and_pyomo() -> None:
    model, elem = _build_poly_model()
    poly_to_py = convert_polyhedron_model(model)

    poly_x = elem.x
    poly_y = elem.y
    py_x = poly_to_py.pyomo_variables[poly_x.name]
    py_y = poly_to_py.pyomo_variables[poly_y.name]

    py_x.set_value(4.25)
    py_y.set_value(1.0)

    values_for_poly = apply_pyomo_values_to_polyhedron(poly_to_py)
    assert pytest.approx(values_for_poly[poly_x], rel=1e-9) == 4.25
    assert pytest.approx(values_for_poly[poly_y], rel=1e-9) == 1.0

    py_to_poly = convert_pyomo_model(poly_to_py.pyomo_model)
    roundtrip_x = py_to_poly.polyhedron_variables[poly_x.name]
    roundtrip_y = py_to_poly.polyhedron_variables[poly_y.name]

    apply_polyhedron_values_to_pyomo(py_to_poly, {roundtrip_x: 2.0, roundtrip_y: 0.0})

    assert pytest.approx(pyomo.value(py_x), rel=1e-9) == 2.0
    assert pytest.approx(pyomo.value(py_y), rel=1e-9) == 0.0


def test_pyomo_roundtrip_preserves_sense_and_variable_types() -> None:
    m = pyomo.ConcreteModel()
    m.flow = pyomo.Var(bounds=(0, 100))
    m.switch = pyomo.Var(domain=pyomo.Binary)
    m.count = pyomo.Var(domain=pyomo.Integers, bounds=(0, 9))

    m.cap = pyomo.Constraint(expr=m.flow <= 10 + 90 * m.switch)
    m.balance = pyomo.Constraint(expr=m.flow >= m.count)
    m.obj = pyomo.Objective(expr=5 * m.flow + 2 * m.count - 3 * m.switch, sense=pyomo.maximize)

    py_to_poly = convert_pyomo_model(m, model_name="py-roundtrip")
    compiled = compile_model(py_to_poly.model)
    assert py_to_poly.model.name == "py-roundtrip"
    assert compiled.objective_sense == "maximize"
    assert len(compiled.variables) == 3

    poly_to_py = convert_polyhedron_model(py_to_poly.model)
    py_vars = poly_to_py.pyomo_variables

    assert py_vars["flow"].is_continuous()
    assert py_vars["switch"].is_binary()
    assert py_vars["count"].is_integer()

    assert pytest.approx(float(py_vars["flow"].lb), rel=1e-9) == 0.0
    assert pytest.approx(float(py_vars["flow"].ub), rel=1e-9) == 100.0
    assert pytest.approx(float(py_vars["count"].lb), rel=1e-9) == 0.0
    assert pytest.approx(float(py_vars["count"].ub), rel=1e-9) == 9.0

    py_vars["flow"].set_value(8.0)
    py_vars["switch"].set_value(1.0)
    py_vars["count"].set_value(4.0)
    values_for_poly = apply_pyomo_values_to_polyhedron(poly_to_py)
    assert len(values_for_poly) == 3


def test_pyomo_bridge_rejects_quadratic_objective() -> None:
    m = pyomo.ConcreteModel()
    m.x = pyomo.Var(bounds=(0, 10))
    m.obj = pyomo.Objective(expr=m.x * m.x, sense=pyomo.minimize)

    with pytest.raises(ValueError, match="linear Pyomo expressions"):
        convert_pyomo_model(m)
