from polyhedron.core.model import Model
from polyhedron.modeling.element import Element
from polyhedron.backends.compiler import compile_model


class Dummy(Element):
    x = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return self.x


def test_compile_model():
    model = Model("compile")
    element = Dummy(name="e1")
    model.add_element(element)

    @model.constraint(name="c1", foreach=[0])
    def constraint(_):
        return element.x >= 0

    compiled = compile_model(model)
    assert len(compiled.variables) == 1
    assert len(compiled.constraints) == 1
    assert len(compiled.objective_terms) == 1
