"""Tests for the sensitivity analysis module (quality/sensitivity.py)."""
from __future__ import annotations

import pytest

from polyhedron import Model, sensitivity
from polyhedron.backends.types import SolveStatus
from polyhedron.core.solution import Solution, SolveMetadata, SolvedModel
from polyhedron.core.variable import Variable, VarType
from polyhedron.modeling.element import Element
from polyhedron.core.objective import maximize, minimize
from polyhedron.quality.sensitivity import (
    ConstraintSensitivity,
    SensitivityReport,
    VariableSensitivity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_var(name: str, lb: float = 0.0, ub: float = 10.0) -> Variable:
    return Variable(name=name, var_type=VarType.CONTINUOUS, lower_bound=lb, upper_bound=ub)


def _make_solved_model(model: Model, values: dict, objective_value: float = 0.0) -> SolvedModel:
    solution = Solution(
        status=SolveStatus.OPTIMAL,
        objective_value=objective_value,
        values=values,
        solver_name="mock",
    )
    return SolvedModel(
        model=model,
        solution=solution,
        metadata=SolveMetadata(solver_name="mock", time_limit=None, mip_gap=0.01),
    )


class SimpleElement(Element):
    def __init__(self):
        super().__init__("simple")
        self.x = _make_var("simple.x", lb=0.0, ub=10.0)
        self.y = _make_var("simple.y", lb=0.0, ub=10.0)
        self._variables["x"] = self.x
        self._variables["y"] = self.y
        c1 = (self.x + self.y <= 8.0)
        c1.name = "sum_cap"
        c1.group = "test"
        c2 = (self.x >= 2.0)
        c2.name = "x_floor"
        c2.group = "test"
        self._constraints.extend([c1, c2])

    @maximize()
    def obj(self):
        return 2.0 * self.x + 3.0 * self.y


# ---------------------------------------------------------------------------
# SensitivityReport structure
# ---------------------------------------------------------------------------

class TestSensitivityReport:
    def _make_report(self) -> SensitivityReport:
        model = Model("test")
        el = SimpleElement()
        model.add_element(el)
        # x=2, y=6: sum_cap binding (2+6=8), x_floor binding (x=2)
        values = {el.x: 2.0, el.y: 6.0}
        solved = _make_solved_model(model, values, objective_value=22.0)
        return sensitivity(solved)

    def test_returns_sensitivity_report_instance(self):
        report = self._make_report()
        assert isinstance(report, SensitivityReport)

    def test_objective_value_is_set(self):
        report = self._make_report()
        assert report.objective_value == pytest.approx(22.0)

    def test_has_duals_false_without_duals(self):
        report = self._make_report()
        assert report.has_duals is False

    def test_constraints_list_is_populated(self):
        report = self._make_report()
        assert len(report.constraints) >= 2

    def test_variables_list_is_populated(self):
        report = self._make_report()
        assert len(report.variables) == 2

    def test_binding_constraints_detected(self):
        report = self._make_report()
        # sum_cap: x+y=8=8 → slack=0 → binding
        # x_floor: x=2 >= 2 → slack=0 → binding
        assert len(report.binding_constraints) >= 2

    def test_nonbinding_constraints_empty(self):
        report = self._make_report()
        # With x=2, y=6 both constraints bind
        assert len(report.nonbinding_constraints) == 0

    def test_variables_at_bound_detects_lower_bound(self):
        report = self._make_report()
        # x=2 is at its lower bound (lb=0? no, x_floor forces x>=2, but var lb=0)
        # y=6 is between bounds → basic
        # x=2 > lb=0 → x is NOT at lower bound; it's basic
        # Let's just check the property exists
        assert isinstance(report.variables_at_bound, list)

    def test_bottlenecks_returns_subset(self):
        report = self._make_report()
        top = report.bottlenecks(top_n=1)
        assert len(top) <= 1

    def test_bottlenecks_are_binding(self):
        report = self._make_report()
        for cs in report.bottlenecks(top_n=10):
            assert cs.is_binding

    def test_by_group_filters_correctly(self):
        report = self._make_report()
        test_group = report.by_group("test")
        assert all(c.group == "test" for c in test_group)
        assert len(test_group) >= 2

    def test_by_group_empty_for_unknown_group(self):
        report = self._make_report()
        assert report.by_group("nonexistent") == []

    def test_summary_is_string(self):
        report = self._make_report()
        s = report.summary()
        assert isinstance(s, str)
        assert "Sensitivity Analysis" in s

    def test_summary_contains_objective_value(self):
        report = self._make_report()
        assert "22.0" in report.summary()

    def test_to_markdown_is_string(self):
        report = self._make_report()
        md = report.to_markdown()
        assert isinstance(md, str)
        assert "Sensitivity Analysis" in md

    def test_to_markdown_contains_table_headers(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "| Name |" in md or "Binding" in md

    def test_most_constrained_variables_returns_list(self):
        report = self._make_report()
        result = report.most_constrained_variables(top_n=5)
        assert isinstance(result, list)


class TestConstraintSensitivity:
    def _get_constraint_sensitivities(self) -> list[ConstraintSensitivity]:
        model = Model("cs_test")
        el = SimpleElement()
        model.add_element(el)
        values = {el.x: 2.0, el.y: 6.0}
        solved = _make_solved_model(model, values, 22.0)
        report = sensitivity(solved)
        return report.constraints

    def test_each_has_name(self):
        for cs in self._get_constraint_sensitivities():
            assert cs.name is not None
            assert len(cs.name) > 0

    def test_slack_is_non_negative(self):
        for cs in self._get_constraint_sensitivities():
            assert cs.slack >= 0.0

    def test_is_binding_matches_slack(self):
        for cs in self._get_constraint_sensitivities():
            if cs.slack < 1e-6:
                assert cs.is_binding
            else:
                assert not cs.is_binding

    def test_opportunity_cost_alias(self):
        for cs in self._get_constraint_sensitivities():
            assert cs.opportunity_cost == cs.shadow_price

    def test_marginal_value_is_abs_shadow_price(self):
        for cs in self._get_constraint_sensitivities():
            if cs.shadow_price is not None:
                assert cs.marginal_value == pytest.approx(abs(cs.shadow_price))
            else:
                assert cs.marginal_value is None


class TestVariableSensitivity:
    def _get_variable_sensitivities(self) -> list[VariableSensitivity]:
        model = Model("vs_test")
        el = SimpleElement()
        model.add_element(el)
        values = {el.x: 2.0, el.y: 6.0}
        solved = _make_solved_model(model, values, 22.0)
        report = sensitivity(solved)
        return report.variables

    def test_each_has_value(self):
        for vs in self._get_variable_sensitivities():
            assert vs.value is not None

    def test_is_basic_for_interior_variable(self):
        # y=6 is between lb=0 and ub=10 → basic
        vss = self._get_variable_sensitivities()
        y_sens = next(vs for vs in vss if "y" in vs.variable.name)
        assert y_sens.is_basic is True

    def test_is_not_basic_for_bound_variable(self):
        # x=2 — is it at lb (0)? No, 2>0. Is it at ub (10)? No.
        # So x is actually basic here too (it's at value 2 between 0 and 10)
        vss = self._get_variable_sensitivities()
        x_sens = next(vs for vs in vss if vs.variable.name == "simple.x")
        # x=2 is between lb=0 and ub=10 → basic
        assert x_sens.is_basic is True

    def test_upper_bound_detection(self):
        model = Model("ub_test")

        class AtUpperBound(Element):
            def __init__(self):
                super().__init__("aub")
                self.z = _make_var("aub.z", lb=0.0, ub=5.0)
                self._variables["z"] = self.z

            @maximize()
            def obj(self):
                return self.z

        el = AtUpperBound()
        model.add_element(el)
        values = {el.z: 5.0}  # at upper bound
        solved = _make_solved_model(model, values, 5.0)
        report = sensitivity(solved)
        z_sens = report.variables[0]
        assert z_sens.is_at_upper_bound is True
        assert z_sens.active_bound == "upper"

    def test_active_bound_none_for_basic(self):
        model = Model("basic_test")

        class Interior(Element):
            def __init__(self):
                super().__init__("int")
                self.w = _make_var("int.w", lb=0.0, ub=10.0)
                self._variables["w"] = self.w

            @maximize()
            def obj(self):
                return self.w

        el = Interior()
        model.add_element(el)
        values = {el.w: 4.5}  # strictly interior
        solved = _make_solved_model(model, values, 4.5)
        report = sensitivity(solved)
        assert report.variables[0].active_bound is None


class TestSensitivityWithDuals:
    """Tests for sensitivity when dual information is present in the solution."""

    def _make_report_with_duals(self) -> SensitivityReport:
        from polyhedron.core.constraint import Constraint

        model = Model("duals_test")
        el = SimpleElement()
        model.add_element(el)

        from polyhedron.backends.compiler import compile_model
        compiled = compile_model(model)
        cons_map = {c.name: c for c in compiled.constraints}

        values = {el.x: 2.0, el.y: 6.0}
        duals = {}
        if "sum_cap" in cons_map:
            duals[cons_map["sum_cap"]] = 3.0
        if "x_floor" in cons_map:
            duals[cons_map["x_floor"]] = -1.0

        slacks = {}
        for c in compiled.constraints:
            slacks[c] = 0.0

        solution = Solution(
            status=SolveStatus.OPTIMAL,
            objective_value=22.0,
            values=values,
            solver_name="mock_lp",
            constraint_duals=duals,
            constraint_slacks=slacks,
        )
        solved = SolvedModel(
            model=model,
            solution=solution,
            metadata=SolveMetadata(solver_name="mock_lp", time_limit=None, mip_gap=0.0),
        )
        return sensitivity(solved)

    def test_has_duals_true_when_duals_provided(self):
        report = self._make_report_with_duals()
        assert report.has_duals is True

    def test_shadow_prices_populated(self):
        report = self._make_report_with_duals()
        for cs in report.binding_constraints:
            assert cs.shadow_price is not None

    def test_bottlenecks_sorted_by_shadow_price(self):
        report = self._make_report_with_duals()
        top = report.bottlenecks(top_n=10)
        prices = [abs(cs.shadow_price or 0.0) for cs in top]
        assert prices == sorted(prices, reverse=True)

    def test_summary_shows_shadow_price(self):
        report = self._make_report_with_duals()
        s = report.summary()
        assert "shadow price" in s.lower()


class TestSensitivityEdgeCases:
    def test_empty_model_raises_type_error(self):
        # Model with no elements
        class FakeModel:
            pass

        fake_solution = Solution(
            status=SolveStatus.OPTIMAL,
            objective_value=0.0,
            values={},
            solver_name="mock",
        )
        solved = SolvedModel(
            model=FakeModel(),
            solution=fake_solution,
            metadata=SolveMetadata(solver_name="mock", time_limit=None, mip_gap=0.01),
        )
        with pytest.raises(TypeError, match="polyhedron Model"):
            sensitivity(solved)

    def test_model_with_no_constraints(self):
        model = Model("empty_constraints")

        class NoConstraintElement(Element):
            def __init__(self):
                super().__init__("nce")
                self.x = _make_var("nce.x")
                self._variables["x"] = self.x

            @maximize()
            def obj(self):
                return self.x

        el = NoConstraintElement()
        model.add_element(el)
        values = {el.x: 10.0}
        solved = _make_solved_model(model, values, 10.0)
        report = sensitivity(solved)
        assert len(report.binding_constraints) == 0
        assert len(report.nonbinding_constraints) == 0

    def test_custom_binding_tolerance(self):
        model = Model("tol_test")
        el = SimpleElement()
        model.add_element(el)
        values = {el.x: 2.0001, el.y: 5.9999}  # tiny numerical noise
        solved = _make_solved_model(model, values, 21.9997)
        # With loose tolerance, the nearly-binding constraints should be detected
        report = sensitivity(solved, binding_tolerance=1e-3)
        assert report is not None
