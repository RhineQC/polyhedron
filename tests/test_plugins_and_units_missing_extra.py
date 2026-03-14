import pytest

from polyhedron.backends.scip.plugins import (
    ScipBranchrulePlugin,
    ScipConstraintHandlerPlugin,
    ScipEventHandlerPlugin,
    ScipPlugin,
    ScipPricerPlugin,
    ScipSeparatorPlugin,
)
from polyhedron.units.dimensions import DIMENSIONLESS, UnitDimension, UnitRegistry


def test_scip_plugin_abstract_raise_lines() -> None:
    class P(ScipPlugin):
        name = "p"
        description = "p"

        def install(self, scip_model, context):
            return super().install(scip_model, context)

    with pytest.raises(NotImplementedError):
        P().install(None, None)

    class E(ScipEventHandlerPlugin):
        name = "e"
        description = "e"

        def build(self, pyscipopt, context):
            return super().build(pyscipopt, context)

        def event_types(self, pyscipopt):
            return super().event_types(pyscipopt)

    e = E()
    with pytest.raises(NotImplementedError):
        e.build(None, None)
    with pytest.raises(NotImplementedError):
        list(e.event_types(None))

    class S(ScipSeparatorPlugin):
        name = "s"
        description = "s"

        def build(self, pyscipopt, context):
            return super().build(pyscipopt, context)

    with pytest.raises(NotImplementedError):
        S().build(None, None)

    class C(ScipConstraintHandlerPlugin):
        name = "c"
        description = "c"

        def build(self, pyscipopt, context):
            return super().build(pyscipopt, context)

    with pytest.raises(NotImplementedError):
        C().build(None, None)

    class B(ScipBranchrulePlugin):
        name = "b"
        description = "b"

        def build(self, pyscipopt, context):
            return super().build(pyscipopt, context)

    with pytest.raises(NotImplementedError):
        B().build(None, None)

    class R(ScipPricerPlugin):
        name = "r"
        description = "r"

        def build(self, pyscipopt, context):
            return super().build(pyscipopt, context)

    with pytest.raises(NotImplementedError):
        R().build(None, None)


def test_units_dimensions_remaining_paths() -> None:
    d = UnitDimension.from_mapping({"m": 1})
    assert str(DIMENSIONLESS) == "1"
    assert (d / d) == DIMENSIONLESS

    reg = UnitRegistry.default()
    # Parse with division and exponent handling.
    out = reg.parse("MW^2/h")
    assert isinstance(out, UnitDimension)

    # Parsing empty token segments should be ignored by _apply.
    out2 = reg.parse("MW//h")
    assert isinstance(out2, UnitDimension)
