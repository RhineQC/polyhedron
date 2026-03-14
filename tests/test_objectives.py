import pytest

from polyhedron import Element, Model, flatten_weighted_objectives, maximize, minimize
from polyhedron.backends.compiler import combine_expressions, compile_model
from polyhedron.core.expression import Expression, QuadraticTerm
from polyhedron.core.objective import objective, scale_expression_like
from polyhedron.core.scenario import ScenarioValues


class WeightedObjectivesElement(Element):
    x = Model.ContinuousVar(min=0, max=10)
    y = Model.ContinuousVar(min=0, max=10)

    @minimize(name="cost", weight=2.0)
    def cost(self):
        return 3 * self.x + self.y

    @maximize(name="satisfaction", weight=0.5)
    def satisfaction(self):
        return self.y


class DecoratorOnlyElement(Element):
    x = Model.ContinuousVar(min=0, max=5)

    @maximize(name="revenue", weight=3.0)
    def revenue(self):
        return self.x


class LegacyObjectiveElement(Element):
    x = Model.ContinuousVar(min=0, max=5)

    def objective_contribution(self):
        return self.x


class MixedObjectiveElement(Element):
    x = Model.ContinuousVar(min=0, max=5)

    def objective_contribution(self):
        return self.x

    @minimize(name="cost")
    def cost(self):
        return 2 * self.x


class NoObjectiveElement(Element):
    x = Model.ContinuousVar(min=0, max=5)


def test_compile_model_flattens_mixed_weighted_objectives() -> None:
    model = Model("multi-objective")
    element = WeightedObjectivesElement("e1")
    model.add_element(element)

    compiled = compile_model(model)

    assert [(objective.name, objective.sense) for objective in compiled.objectives] == [
        ("cost", "minimize"),
        ("satisfaction", "maximize"),
    ]
    assert compiled.objective_sense == "minimize"

    objective_expr = combine_expressions(compiled.objective_terms)
    assert isinstance(objective_expr, Expression)
    coefficients = {}
    for var, coef in objective_expr.terms:
        coefficients[var.name] = coefficients.get(var.name, 0.0) + coef
    assert coefficients[element.x.name] == pytest.approx(6.0)
    assert coefficients[element.y.name] == pytest.approx(1.5)

    flattened_terms, flattened_sense = flatten_weighted_objectives(compiled.objectives)
    assert flattened_terms == compiled.objective_terms
    assert flattened_sense == compiled.objective_sense


def test_decorator_only_element_does_not_require_legacy_method() -> None:
    model = Model("decorator-only")
    element = DecoratorOnlyElement("e1")
    model.add_element(element)

    compiled = compile_model(model)

    assert len(compiled.objectives) == 1
    assert compiled.objectives[0].name == "revenue"
    assert compiled.objective_sense == "maximize"


def test_legacy_objective_contribution_remains_supported() -> None:
    model = Model("legacy-objective")
    model.objective_sense = "maximize"
    element = LegacyObjectiveElement("e1")
    model.add_element(element)

    compiled = compile_model(model)

    assert len(compiled.objectives) == 1
    assert compiled.objectives[0].name == "primary"
    assert compiled.objective_sense == "maximize"


def test_mixing_legacy_and_decorated_objectives_raises_clear_error() -> None:
    model = Model("mixed-objective-styles")
    element = MixedObjectiveElement("e1")
    model.add_element(element)

    with pytest.raises(ValueError, match="mixes @objective-decorated methods"):
        compile_model(model)


def test_compile_model_with_no_objectives_keeps_model_sense() -> None:
    model = Model("no-objectives")
    model.objective_sense = "maximize"
    model.add_element(NoObjectiveElement("e1"))

    compiled = compile_model(model)

    assert compiled.objectives == []
    assert compiled.objective_terms == []
    assert compiled.objective_sense == "maximize"


def test_flatten_weighted_objectives_handles_empty_input() -> None:
    terms, sense = flatten_weighted_objectives([])

    assert terms == []
    assert sense == "minimize"


def test_objective_decorator_validates_sense_and_weight() -> None:
    with pytest.raises(ValueError, match="Unsupported objective sense"):
        objective(name="bad", sense="sideways")

    with pytest.raises(ValueError, match="finite positive"):
        minimize(name="bad-weight", weight=0.0)


def test_scale_expression_like_supports_variable_quadratic_scenario_and_numbers() -> None:
    x = Model.BinaryVar().create_variable("x")
    y = Model.BinaryVar().create_variable("y")

    scaled_var = scale_expression_like(x, 3.0)
    assert isinstance(scaled_var, Expression)
    assert scaled_var.terms == [(x, 3.0)]

    scaled_quadratic = scale_expression_like(QuadraticTerm(x, y, coefficient=2.0), -4.0)
    assert isinstance(scaled_quadratic, QuadraticTerm)
    assert scaled_quadratic.coefficient == pytest.approx(-8.0)

    scenario = ScenarioValues({"base": 1.0, "stress": 2.0})
    scaled_scenario = scale_expression_like(scenario, 0.5)
    assert isinstance(scaled_scenario, Expression)
    assert scaled_scenario.scenario_terms == [(scenario, 0.5)]

    assert scale_expression_like(2.0, 1.5) == pytest.approx(3.0)

    with pytest.raises(TypeError, match="Unsupported objective term type"):
        scale_expression_like(object(), 2.0)  # type: ignore[arg-type]
