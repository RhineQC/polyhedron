import sys

import pytest

from polyhedron.backends.compiler import CompiledModel
from polyhedron.backends.highs import HighsBackend
from polyhedron.backends.scip.plugins import (
    ScipBranchrulePlugin,
    ScipConstraintHandlerPlugin,
    ScipEventHandlerPlugin,
    ScipHookContext,
    ScipPricerPlugin,
    ScipSeparatorPlugin,
)


class DummyScipModel:
    def __init__(self):
        self.calls = []

    def includeEventhdlr(self, handler, name, description):
        self.calls.append(("includeEventhdlr", handler, name, description))

    def catchEvent(self, event_type, handler):
        self.calls.append(("catchEvent", event_type, handler))

    def includeSepa(self, *args):
        self.calls.append(("includeSepa",) + args)

    def includeConshdlr(self, *args):
        self.calls.append(("includeConshdlr",) + args)

    def includeBranchrule(self, *args):
        self.calls.append(("includeBranchrule",) + args)

    def includePricer(self, *args):
        self.calls.append(("includePricer",) + args)


class EventPlugin(ScipEventHandlerPlugin):
    name = "evt"
    description = "event"

    def build(self, pyscipopt, context):
        return "handler"

    def event_types(self, pyscipopt):
        return ["A", "B"]


class SeparatorPlugin(ScipSeparatorPlugin):
    name = "sepa"
    description = "separator"

    def build(self, pyscipopt, context):
        return "sepa_obj"


class ConstraintPlugin(ScipConstraintHandlerPlugin):
    name = "cons"
    description = "constraint"

    def build(self, pyscipopt, context):
        return "cons_obj"


class BranchPlugin(ScipBranchrulePlugin):
    name = "branch"
    description = "branching"

    def build(self, pyscipopt, context):
        return "branch_obj"


class PricerPlugin(ScipPricerPlugin):
    name = "pricer"
    description = "pricing"

    def build(self, pyscipopt, context):
        return "pricer_obj"


def _ctx() -> ScipHookContext:
    return ScipHookContext(
        model=object(),
        var_map={},
        compiled=CompiledModel(variables=[], constraints=[], objective_terms=[], objective_sense="minimize"),
        debug_hooks=None,
    )


def test_highs_backend_not_implemented() -> None:
    backend = HighsBackend()
    assert backend.name == "highs"


def test_scip_plugins_install_with_fake_pyscipopt(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pyscipopt", object())
    model = DummyScipModel()
    context = _ctx()

    EventPlugin().install(model, context)
    SeparatorPlugin().install(model, context)
    ConstraintPlugin().install(model, context)
    BranchPlugin().install(model, context)
    PricerPlugin().install(model, context)

    tags = [call[0] for call in model.calls]
    assert "includeEventhdlr" in tags
    assert tags.count("catchEvent") == 2
    assert "includeSepa" in tags
    assert "includeConshdlr" in tags
    assert "includeBranchrule" in tags
    assert "includePricer" in tags


def test_event_plugin_install_raises_when_model_missing_support(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pyscipopt", object())

    class NoEvents:
        pass

    with pytest.raises(RuntimeError, match="does not support event handlers"):
        EventPlugin().install(NoEvents(), _ctx())


def test_other_plugin_runtime_errors_when_model_missing_support(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pyscipopt", object())

    class NoSepa:
        pass

    class NoConshdlr:
        pass

    class NoBranch:
        pass

    class NoPricer:
        pass

    with pytest.raises(RuntimeError, match="does not support separators"):
        SeparatorPlugin().install(NoSepa(), _ctx())
    with pytest.raises(RuntimeError, match="does not support constraint handlers"):
        ConstraintPlugin().install(NoConshdlr(), _ctx())
    with pytest.raises(RuntimeError, match="does not support branch rules"):
        BranchPlugin().install(NoBranch(), _ctx())
    with pytest.raises(RuntimeError, match="does not support pricers"):
        PricerPlugin().install(NoPricer(), _ctx())
