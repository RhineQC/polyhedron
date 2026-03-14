from polyhedron.core.model import Model
from polyhedron.modeling.element import Element


class HElement(Element):
    x = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return self.x


def test_model_heuristic_mapping_priority_frequency_paths() -> None:
    model = Model("hm")
    model.add_element(HElement("e"))

    calls = []

    @model.heuristic(priority=200, frequency="root")
    def h_critical(ctx):
        calls.append(("critical", bool(ctx is not None)))
        return None

    @model.heuristic(priority=80, frequency="SOLUTION")
    def h_high(ctx):
        calls.append(("high", bool(ctx is not None)))
        return None

    @model.heuristic(priority=50, frequency="periodic")
    def h_medium(ctx):
        calls.append(("medium", bool(ctx is not None)))
        return None

    @model.heuristic(priority=25, frequency="adaptive")
    def h_low(ctx):
        calls.append(("low", bool(ctx is not None)))
        return None

    @model.heuristic(priority=1, frequency="unknown")
    def h_minimal(ctx):
        calls.append(("minimal", bool(ctx is not None)))
        return None

    model._materialize_decorated_heuristics()
    assert model.heuristics == []
    assert len(model.intelligence) == 5

    dummy_ctx = object()
    for h in model.intelligence:
        h.apply(dummy_ctx)

    assert len(calls) == 5
