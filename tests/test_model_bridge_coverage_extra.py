"""Tests covering model.py constraint foreach iterable path and pyomo bridge >= sense."""
from __future__ import annotations

import pytest

from polyhedron import Model
from polyhedron.core.constraint import Constraint
from polyhedron.core.variable import Variable, VarType
from polyhedron.modeling.element import Element
from polyhedron.core.objective import maximize


# ---------------------------------------------------------------------------
# core/model.py: constraint decorator with foreach returning iterables
# ---------------------------------------------------------------------------

class ForeachElement(Element):
    x = Model.ContinuousVar(min=0.0, max=100.0)

    def objective_contribution(self):
        return 0


class TestConstraintForeachIterable:
    def test_foreach_returns_list_of_constraints(self):
        """@constraint(foreach=...) where func returns a list of Constraints (lines 138-141)."""
        model = Model("foreach-iter")
        el = ForeachElement("fe1")
        model.add_element(el)

        limits = [20.0, 50.0, 80.0]

        @model.constraint(foreach=limits, name="limit")
        def bounds(cap):
            # Return a LIST of constraints instead of a single Constraint
            return [Constraint(lhs=el.x, sense="<=", rhs=cap)]

        # Each foreach item yields a list with 1 constraint → 3 constraints total
        assert len(model.constraints) == 3

    def test_foreach_returns_mixed_iterable(self):
        """@constraint(foreach=...) where func returns multiple constraints per item."""
        model = Model("foreach-multi")
        el = ForeachElement("fe2")
        model.add_element(el)

        @model.constraint(foreach=[1, 2], name="pair")
        def multi(i):
            return [
                Constraint(lhs=el.x, sense="<=", rhs=float(i * 10)),
                Constraint(lhs=el.x, sense=">=", rhs=0.0),
            ]

        # 2 items × 2 constraints each = 4 constraints
        assert len(model.constraints) == 4

    def test_foreach_single_constraint_not_iterable(self):
        """@constraint(foreach=...) where func returns a single Constraint."""
        model = Model("foreach-single")
        el = ForeachElement("fe3")
        model.add_element(el)

        @model.constraint(foreach=[5.0, 10.0], name="cap")
        def single_con(cap):
            return el.x <= cap

        assert len(model.constraints) == 2

    def test_foreach_constraint_name_preserved(self):
        """Constraints from foreach retain the decorator name if not already set."""
        model = Model("foreach-names")
        el = ForeachElement("fe4")
        model.add_element(el)

        @model.constraint(foreach=[99.0], name="named_lim")
        def named(cap):
            return [Constraint(lhs=el.x, sense="<=", rhs=cap)]

        assert model.constraints[0].name == "named_lim"


# ---------------------------------------------------------------------------
# bridges/pyomo.py: >= constraint sense coverage
# ---------------------------------------------------------------------------

class GeqElement(Element):
    x = Model.ContinuousVar(min=0.0, max=10.0)

    @maximize()
    def obj(self):
        return self.x


class TestPyomoBridgeGeqConstraint:
    def test_convert_polyhedron_geq_constraint(self):
        """convert_polyhedron_model with >= constraint triggers elif line 281."""
        try:
            import pyomo  # noqa: F401
        except ImportError:
            pytest.skip("pyomo not installed")

        from polyhedron.bridges.pyomo import convert_polyhedron_model

        model = Model("pyomo-geq")
        el = GeqElement("pg1")
        model.add_element(el)

        @model.constraint(name="lower_floor")
        def lower_floor():
            return el.x >= 2.0  # >= constraint → line 281 in convert_polyhedron_model

        result = convert_polyhedron_model(model)
        assert result.pyomo_model is not None

    def test_convert_polyhedron_eq_constraint(self):
        """convert_polyhedron_model with == constraint."""
        try:
            import pyomo  # noqa: F401
        except ImportError:
            pytest.skip("pyomo not installed")

        from polyhedron.bridges.pyomo import convert_polyhedron_model

        model = Model("pyomo-eq")
        el = GeqElement("pe1")
        model.add_element(el)

        @model.constraint(name="eq_con")
        def eq_con():
            return el.x == 5.0  # == constraint

        result = convert_polyhedron_model(model)
        assert result.pyomo_model is not None

    def test_convert_polyhedron_leq_constraint(self):
        """convert_polyhedron_model with <= constraint."""
        try:
            import pyomo  # noqa: F401
        except ImportError:
            pytest.skip("pyomo not installed")

        from polyhedron.bridges.pyomo import convert_polyhedron_model

        model = Model("pyomo-leq")
        el = GeqElement("pl1")
        model.add_element(el)

        @model.constraint(name="leq_con")
        def leq_con():
            return el.x <= 8.0

        result = convert_polyhedron_model(model)
        assert result.pyomo_model is not None
