import builtins
from types import SimpleNamespace

import pytest

from polyhedron.core.scenario import ScenarioValues
from polyhedron.core.validation import _is_operand, validate_model
from polyhedron.intelligence.branching import BranchingStrategy
from polyhedron.intelligence.context import SolverContext
from polyhedron.intelligence.heuristics import HeuristicBase, Priority
from polyhedron.intelligence.simple_rounding import SimpleRoundingHeuristic


def test_scenario_operator_paths() -> None:
    s = ScenarioValues({"a": 1.0, "b": 2.0})

    add_expr = s + 1
    radd_expr = 1 + s
    rsub_expr = 10 - s
    neg_expr = -s

    assert add_expr is not None
    assert radd_expr is not None
    assert rsub_expr is not None
    assert neg_expr is not None


def test_validation_import_fallback_and_empty_model_issue(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "polyhedron.core.scenario":
            raise ImportError("blocked")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert _is_operand(1)

    class Empty:
        name = "empty"
        elements = []
        constraints = []

        @staticmethod
        def materialize_constraints():
            return None

    issues = validate_model(Empty())
    assert any(i.code == "E001" for i in issues)


def test_heuristics_should_apply_false_paths_and_abstract_raise() -> None:
    class Concrete(HeuristicBase):
        def __init__(self, **kwargs):
            super().__init__(name="c", **kwargs)

        def apply(self, context):
            return None

    disabled = Concrete(enabled=False)
    assert disabled.should_apply(SimpleNamespace(depth=0)) is False

    depth_limited = Concrete(max_depth=1)
    assert depth_limited.should_apply(SimpleNamespace(depth=2)) is False

    class AbstractViaSuper(HeuristicBase):
        def __init__(self):
            super().__init__(name="a", priority=Priority.MEDIUM)

        def apply(self, context):
            return super().apply(context)

    with pytest.raises(NotImplementedError):
        AbstractViaSuper().apply(SolverContext(model=object()))


def test_simple_rounding_none_path_and_branching_fallback() -> None:
    h = SimpleRoundingHeuristic()
    assert h.apply(SolverContext(model=object(), current_relaxation=None)) is None

    class SlotVar:
        __slots__ = ("name", "_branching_priority")

        def __init__(self, name):
            self.name = name

    v = SlotVar("x_plant")
    BranchingStrategy(rule="name", priorities={"plant": 4}).apply(model=None, variables=[v])
    assert v._branching_priority == 4
