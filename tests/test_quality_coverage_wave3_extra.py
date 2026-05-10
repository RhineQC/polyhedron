"""Extra tests covering remaining gaps in quality module coverage."""
from __future__ import annotations

import pytest

from polyhedron import Model
from polyhedron.backends.types import SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.core.objective import maximize, minimize
from polyhedron.core.solution import Solution, SolveMetadata, SolvedModel
from polyhedron.core.variable import Variable, VarType
from polyhedron.modeling.element import Element
from polyhedron.quality.sensitivity import (
    ConstraintSensitivity,
    SensitivityReport,
    VariableSensitivity,
    sensitivity,
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


# ---------------------------------------------------------------------------
# quality/_analysis.py gaps
# ---------------------------------------------------------------------------

class TestAnalysisGaps:
    def test_to_expression_raises_type_error_for_unsupported(self):
        from polyhedron.quality._analysis import to_expression
        with pytest.raises(TypeError):
            to_expression(object())

    def test_expression_coefficient_range_with_terms(self):
        from polyhedron.quality._analysis import expression_coefficient_range
        from polyhedron.core.expression import Expression
        x = _make_var("range_x", lb=0.0, ub=10.0)
        expr = Expression([(x, 3.0)])
        lo, hi = expression_coefficient_range(expr)
        assert lo == pytest.approx(3.0)
        assert hi == pytest.approx(3.0)

    def test_expression_coefficient_range_empty_expression(self):
        """expression_coefficient_range with no terms returns (0.0, 0.0) (line 57)."""
        from polyhedron.quality._analysis import expression_coefficient_range
        from polyhedron.core.expression import Expression
        expr = Expression()
        lo, hi = expression_coefficient_range(expr)
        assert lo == 0.0
        assert hi == 0.0

    def test_safe_ratio_zero_denominator_nonzero_numerator(self):
        """safe_ratio with denominator=0 and numerator!=0 returns inf (line 92)."""
        from polyhedron.quality._analysis import safe_ratio
        result = safe_ratio(1.0, 0.0)
        assert result == float("inf")

    def test_safe_ratio_zero_denominator_zero_numerator(self):
        """safe_ratio with denominator=0 and numerator=0 returns 1.0 (line 92)."""
        from polyhedron.quality._analysis import safe_ratio
        result = safe_ratio(0.0, 0.0)
        assert result == 1.0

    def test_evaluate_constraint_violation_geq_sense(self):
        from polyhedron.quality._analysis import evaluate_constraint_violation
        x = _make_var("cv_x", lb=0.0, ub=10.0)
        # x >= 5 but x=3 → violation > 0
        cons = (x >= 5.0)
        violation = evaluate_constraint_violation(cons, {x: 3.0})
        assert violation > 0.0

    def test_evaluate_constraint_violation_geq_satisfied(self):
        from polyhedron.quality._analysis import evaluate_constraint_violation
        x = _make_var("cv_x2", lb=0.0, ub=10.0)
        # x >= 2 and x=5 → no violation
        cons = (x >= 2.0)
        violation = evaluate_constraint_violation(cons, {x: 5.0})
        assert violation == 0.0

    def test_evaluate_constraint_violation_eq_sense(self):
        from polyhedron.quality._analysis import evaluate_constraint_violation
        x = _make_var("cv_eq", lb=0.0, ub=10.0)
        # x == 5 but x=3 → violation = |3-5| - tol
        cons = (x == 5.0)
        violation = evaluate_constraint_violation(cons, {x: 3.0})
        assert violation > 0.0

    def test_evaluate_constraint_violation_unknown_sense(self):
        from polyhedron.quality._analysis import evaluate_constraint_violation
        x = _make_var("cv_unk", lb=0.0, ub=10.0)
        cons = Constraint(lhs=x, sense="~=", rhs=5.0)
        result = evaluate_constraint_violation(cons, {x: 3.0})
        assert result == float("inf")


# ---------------------------------------------------------------------------
# quality/linter.py gaps: private functions
# ---------------------------------------------------------------------------

class TestLinterPrivateFunctions:
    def test_should_colorize_never(self):
        from polyhedron.quality.linter import _should_colorize
        assert _should_colorize("never") is False

    def test_should_colorize_always(self):
        from polyhedron.quality.linter import _should_colorize
        assert _should_colorize("always") is True

    def test_should_colorize_auto_returns_bool(self):
        from polyhedron.quality.linter import _should_colorize
        result = _should_colorize("auto")
        assert isinstance(result, bool)

    def test_should_colorize_invalid_raises(self):
        from polyhedron.quality.linter import _should_colorize
        with pytest.raises(ValueError, match="color must be"):
            _should_colorize("invalid_value")

    def test_colorize_no_color_returns_plain_text(self):
        from polyhedron.quality.linter import _colorize, LintSeverity
        result = _colorize("TEST", LintSeverity.ERROR, use_color=False)
        assert result == "TEST"

    def test_colorize_info_returns_blue_ansi(self):
        from polyhedron.quality.linter import _colorize, LintSeverity
        result = _colorize("MSG", LintSeverity.INFO, use_color=True)
        assert "\x1b[34m" in result
        assert "MSG" in result

    def test_colorize_warning_returns_yellow_ansi(self):
        from polyhedron.quality.linter import _colorize, LintSeverity
        result = _colorize("WARN", LintSeverity.WARNING, use_color=True)
        assert "\x1b[33m" in result

    def test_colorize_error_returns_red_ansi(self):
        from polyhedron.quality.linter import _colorize, LintSeverity
        result = _colorize("ERR", LintSeverity.ERROR, use_color=True)
        assert "\x1b[31m" in result


# ---------------------------------------------------------------------------
# quality/linter.py gaps: lint_model coverage paths
# ---------------------------------------------------------------------------

class BoundsElement(Element):
    """Element whose variable bounds can be customized via class-level vars."""
    x = Model.ContinuousVar(min=0.0)  # no max → upper = inf

    def objective_contribution(self):
        return 0


class WideBoundsElement(Element):
    x = Model.ContinuousVar(min=0.0, max=2e9)  # wide but finite span > 1e8

    def objective_contribution(self):
        return 0


class DominatedElement(Element):
    x = Model.ContinuousVar(min=0.0, max=100.0)

    def objective_contribution(self):
        return 0


class UnboundedObjElement(Element):
    x = Model.ContinuousVar(min=0.0)  # no upper → inf

    @maximize()
    def obj(self):
        return 2.0 * self.x  # maximize with positive coef + no upper bound → unbounded


class UnboundedMinNegElement(Element):
    x = Model.ContinuousVar(min=0.0)  # no upper → inf

    @minimize()
    def obj(self):
        return -2.0 * self.x  # minimize with negative coef + no upper bound → unbounded


class TestLinterCoveragePaths:
    def test_lint_with_scaling_ratio_threshold(self):
        from polyhedron.quality import lint_model
        model = Model("scaling-threshold")
        elem = DominatedElement("sc1")
        model.add_element(elem)

        @model.constraint(name="con")
        def c():
            return elem.x <= 50.0

        # scaling_ratio_threshold triggers lines 212-214
        report = lint_model(model, scaling_ratio_threshold=1e6)
        assert isinstance(report.issues, list)

    def test_lint_dominated_duplicate_constraint(self):
        from polyhedron.quality import lint_model
        model = Model("dominated-dup")
        elem = DominatedElement("d1")
        model.add_element(elem)

        # Add x <= 5 first (tighter), then x <= 10 (weaker → dominated by x<=5)
        @model.constraint(name="tight")
        def tight():
            return elem.x <= 5.0

        @model.constraint(name="weak")
        def weak():
            return elem.x <= 10.0

        report = lint_model(model)
        codes = {issue.code for issue in report.issues}
        assert "LINT_DOMINATED_DUPLICATE" in codes

    def test_lint_dominated_duplicate_geq_constraint(self):
        from polyhedron.quality import lint_model
        model = Model("dominated-geq")
        elem = DominatedElement("d2")
        model.add_element(elem)

        # Add x >= 5 first (tighter), then x >= 2 (weaker → dominated by x>=5)
        @model.constraint(name="tight_geq")
        def tight_geq():
            return elem.x >= 5.0

        @model.constraint(name="weak_geq")
        def weak_geq():
            return elem.x >= 2.0

        report = lint_model(model)
        codes = {issue.code for issue in report.issues}
        assert "LINT_DOMINATED_DUPLICATE" in codes

    def test_lint_infinite_bound_variable_continue_path(self):
        """Variable with infinite bound triggers _append_issue then continue."""
        from polyhedron.quality import lint_model
        model = Model("inf-bound")
        elem = BoundsElement("b1")
        model.add_element(elem)

        @model.constraint(name="use_x")
        def use_x():
            return elem.x <= 100.0

        report = lint_model(model)
        codes = {issue.code for issue in report.issues}
        assert "LINT_WEAK_BOUNDS" in codes

    def test_lint_wide_finite_bound_variable(self):
        """Variable with span > 1e8 triggers wide-bounds warning."""
        from polyhedron.quality import lint_model
        model = Model("wide-bound")
        elem = WideBoundsElement("wb1")
        model.add_element(elem)

        @model.constraint(name="use_wide")
        def use_wide():
            return elem.x <= 1e9

        report = lint_model(model)
        codes = {issue.code for issue in report.issues}
        assert "LINT_WEAK_BOUNDS" in codes

    def test_lint_objective_unbounded_risk_maximize_positive_coef(self):
        """Maximize with positive coef and no upper bound → unbounded risk."""
        from polyhedron.quality import lint_model
        model = Model("unbound-max-pos")
        elem = UnboundedObjElement("u1")
        model.add_element(elem)
        report = lint_model(model)
        codes = {issue.code for issue in report.issues}
        assert "LINT_OBJECTIVE_UNBOUNDED_RISK" in codes

    def test_lint_objective_unbounded_risk_minimize_negative_coef(self):
        """Minimize with negative coef and no upper bound → unbounded risk."""
        from polyhedron.quality import lint_model
        model = Model("unbound-min-neg")
        elem = UnboundedMinNegElement("u2")
        model.add_element(elem)
        report = lint_model(model)
        codes = {issue.code for issue in report.issues}
        assert "LINT_OBJECTIVE_UNBOUNDED_RISK" in codes

    def test_lint_to_ansi_with_always_color(self):
        """to_ansi with color='always' exercises _should_colorize('always')."""
        from polyhedron.quality import lint_model
        model = Model("ansi-always")
        elem = BoundsElement("ba1")
        model.add_element(elem)

        @model.constraint(name="use_for_ansi")
        def use_for_ansi():
            return elem.x <= 50.0

        report = lint_model(model)
        text = report.to_ansi(color="always")
        assert isinstance(text, str)

    def test_lint_to_ansi_with_never_color(self):
        """to_ansi with color='never' exercises _should_colorize('never')."""
        from polyhedron.quality import lint_model
        model = Model("ansi-never")
        elem = BoundsElement("bn1")
        model.add_element(elem)

        @model.constraint(name="use_for_ansi2")
        def use_for_ansi2():
            return elem.x <= 50.0

        report = lint_model(model)
        text = report.to_ansi(color="never")
        assert "\x1b[" not in text

    def test_lint_objective_zero_coef_hits_continue(self):
        """Objective term with coef 0.0 should hit the early continue branch."""
        from polyhedron.quality import lint_model

        class ZeroCoefObjElement(Element):
            x = Model.ContinuousVar(min=0.0)

            @maximize()
            def obj(self):
                return 0.0 * self.x

        model = Model("unbound-zero-coef")
        elem = ZeroCoefObjElement("uz0")
        model.add_element(elem)
        report = lint_model(model)
        codes = {issue.code for issue in report.issues}
        assert "LINT_OBJECTIVE_UNBOUNDED_RISK" not in codes

    def test_lint_objective_unbounded_risk_minimize_positive_coef(self):
        """Minimize with positive coef and -inf lower bound should trigger risk."""
        from polyhedron.backends.compiler import CompiledModel
        from polyhedron.core.expression import Expression
        from polyhedron.quality import linter as linter_mod
        from polyhedron.quality.linter import lint_model

        x = Variable("min_pos_var", VarType.CONTINUOUS, lower_bound=float("-inf"), upper_bound=10.0)
        compiled = CompiledModel(
            variables=[x],
            constraints=[],
            objective_terms=[Expression([(x, 1.0)])],
            objective_sense="minimize",
            objectives=[],
        )

        original_compile_model = linter_mod.compile_model
        linter_mod.compile_model = lambda _model: compiled
        try:
            report = lint_model(object())
        finally:
            linter_mod.compile_model = original_compile_model

        codes = {issue.code for issue in report.issues}
        assert "LINT_OBJECTIVE_UNBOUNDED_RISK" in codes

    def test_lint_objective_unbounded_risk_maximize_negative_coef(self):
        """Maximize with negative coef and -inf lower bound should trigger risk."""
        from polyhedron.backends.compiler import CompiledModel
        from polyhedron.core.expression import Expression
        from polyhedron.quality import linter as linter_mod
        from polyhedron.quality.linter import lint_model

        x = Variable("max_neg_var", VarType.CONTINUOUS, lower_bound=float("-inf"), upper_bound=10.0)
        compiled = CompiledModel(
            variables=[x],
            constraints=[],
            objective_terms=[Expression([(x, -1.0)])],
            objective_sense="maximize",
            objectives=[],
        )

        original_compile_model = linter_mod.compile_model
        linter_mod.compile_model = lambda _model: compiled
        try:
            report = lint_model(object())
        finally:
            linter_mod.compile_model = original_compile_model

        codes = {issue.code for issue in report.issues}
        assert "LINT_OBJECTIVE_UNBOUNDED_RISK" in codes

    def test_summary_info_counter_branch(self):
        """Force summary.info increment branch with a synthetic INFO issue."""
        from polyhedron.quality import linter as linter_mod
        from polyhedron.quality.linter import LintCategory, LintSeverity, lint_model

        original_append = linter_mod._append_issue

        def wrapped_append(issues, **kwargs):
            if kwargs.get("code") == "LINT_WEAK_BOUNDS":
                original_append(
                    issues,
                    code="LINT_TEST_INFO",
                    severity=LintSeverity.INFO,
                    category=LintCategory.MODELING,
                    message="Synthetic info for branch coverage.",
                )
            return original_append(issues, **kwargs)

        linter_mod._append_issue = wrapped_append
        try:
            model = Model("lint-info")
            elem = WideBoundsElement("wi1")
            model.add_element(elem)

            @model.constraint(name="c_info")
            def c_info():
                return elem.x <= 10.0

            report = lint_model(model)
            assert report.summary.info >= 1
        finally:
            linter_mod._append_issue = original_append


# ---------------------------------------------------------------------------
# quality/sensitivity.py gaps
# ---------------------------------------------------------------------------

class TestSensitivityGaps:
    def test_active_bound_returns_lower_for_lb_variable(self):
        """active_bound == 'lower' when is_at_lower_bound=True (line 74)."""
        var = _make_var("lb_var", lb=0.0, ub=10.0)
        vs = VariableSensitivity(
            variable=var,
            value=0.0,
            reduced_cost=None,
            is_at_lower_bound=True,
            is_at_upper_bound=False,
        )
        assert vs.active_bound == "lower"
        assert vs.is_basic is False

    def test_sensitivity_summary_no_binding_constraints(self):
        """summary() 'No binding constraints detected.' branch (line 180)."""
        model = Model("no-bind")

        class LooseElement(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            @maximize()
            def obj(self):
                return self.x

        el = LooseElement("le1")
        model.add_element(el)

        @model.constraint(name="loose_con")
        def loose_con():
            return el.x <= 10.0  # not binding when x < 10

        values = {el.x: 3.0}  # slack = 7 > 0
        solved = _make_solved_model(model, values, 3.0)
        report = sensitivity(solved)
        assert len(report.binding_constraints) == 0
        s = report.summary()
        assert "No binding constraints detected." in s

    def test_sensitivity_to_markdown_no_binding_constraints(self):
        """to_markdown() '_No binding constraints._' branch."""
        model = Model("no-bind-md")

        class LooseMd(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            @maximize()
            def obj(self):
                return self.x

        el = LooseMd("lm1")
        model.add_element(el)

        @model.constraint(name="loose_md")
        def loose_md():
            return el.x <= 10.0

        values = {el.x: 5.0}
        solved = _make_solved_model(model, values, 5.0)
        report = sensitivity(solved)
        md = report.to_markdown()
        assert "_No binding constraints._" in md

    def test_sensitivity_summary_with_duals_and_bound_vars(self):
        """summary() lines 186-188: has_duals=True + variables at bound."""
        var = _make_var("sv_x", lb=0.0, ub=10.0)
        vs = VariableSensitivity(
            variable=var,
            value=0.0,
            reduced_cost=3.5,
            is_at_lower_bound=True,
            is_at_upper_bound=False,
        )
        cons = Constraint(lhs=var, sense="<=", rhs=10.0)
        cons.name = "sc"
        cs = ConstraintSensitivity(
            constraint=cons,
            name="sc",
            shadow_price=2.0,
            slack=0.0,
            is_binding=True,
            group=None,
        )
        report = SensitivityReport(
            objective_value=42.0,
            has_duals=True,
            constraints=[cs],
            variables=[vs],
        )
        s = report.summary()
        assert "most constrained" in s.lower() or "sv_x" in s

    def test_sensitivity_to_markdown_with_bound_vars(self):
        """to_markdown() with variables at bound renders var table."""
        var = _make_var("md_x", lb=0.0, ub=10.0)
        vs = VariableSensitivity(
            variable=var,
            value=0.0,
            reduced_cost=1.0,
            is_at_lower_bound=True,
            is_at_upper_bound=False,
        )
        cons = Constraint(lhs=var, sense="<=", rhs=10.0)
        cons.name = "mc"
        cs = ConstraintSensitivity(
            constraint=cons,
            name="mc",
            shadow_price=None,
            slack=0.0,
            is_binding=True,
            group=None,
        )
        report = SensitivityReport(
            objective_value=10.0,
            has_duals=False,
            constraints=[cs],
            variables=[vs],
        )
        md = report.to_markdown()
        assert "md_x" in md

    def test_most_constrained_variables_with_duals(self):
        """most_constrained_variables sorted by reduced_cost when has_duals=True."""
        var1 = _make_var("mc_a", lb=0.0, ub=5.0)
        var2 = _make_var("mc_b", lb=0.0, ub=5.0)
        vs1 = VariableSensitivity(
            variable=var1, value=0.0, reduced_cost=2.0,
            is_at_lower_bound=True, is_at_upper_bound=False,
        )
        vs2 = VariableSensitivity(
            variable=var2, value=5.0, reduced_cost=5.0,
            is_at_lower_bound=False, is_at_upper_bound=True,
        )
        report = SensitivityReport(
            objective_value=0.0,
            has_duals=True,
            constraints=[],
            variables=[vs1, vs2],
        )
        result = report.most_constrained_variables(top_n=10)
        # Should be sorted by |reduced_cost| descending: vs2 (5.0) then vs1 (2.0)
        assert len(result) == 2
        assert result[0].reduced_cost == pytest.approx(5.0)

    def test_sensitivity_with_geq_constraint_computes_slack(self):
        """sensitivity() with >= constraint where raw_slack is None (line 300)."""
        model = Model("geq-slack")

        class GeqElement(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            @maximize()
            def obj(self):
                return self.x

        el = GeqElement("geq1")
        model.add_element(el)

        @model.constraint(name="lower_floor")
        def lower_floor():
            return el.x >= 3.0

        values = {el.x: 7.0}  # x=7 >= 3 → slack = 7-3 = 4 > 0 (not binding)
        solved = _make_solved_model(model, values, 7.0)
        report = sensitivity(solved)
        # Verify the >= constraint has a non-negative slack
        floor_cs = next(
            (cs for cs in report.constraints if cs.name == "lower_floor"), None
        )
        assert floor_cs is not None
        assert floor_cs.slack >= 0.0

    def test_sensitivity_with_eq_constraint_computes_slack(self):
        """sensitivity() with == constraint where raw_slack uses abs() path (line 300)."""
        model = Model("eq-slack")

        class EqElement(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            @maximize()
            def obj(self):
                return self.x

        el = EqElement("eq1")
        model.add_element(el)

        @model.constraint(name="equality_con")
        def equality_con():
            return el.x == 5.0  # == constraint

        values = {el.x: 5.0}  # exactly satisfies x=5
        solved = _make_solved_model(model, values, 5.0)
        report = sensitivity(solved)
        eq_cs = next(
            (cs for cs in report.constraints if cs.name == "equality_con"), None
        )
        assert eq_cs is not None
        assert eq_cs.slack == pytest.approx(0.0)  # binding (x=5 satisfies x==5)

    def test_bottlenecks_no_duals_returns_binding_slice(self):
        """bottlenecks() when has_duals=False returns binding[:top_n]."""
        var = _make_var("bn_x", lb=0.0, ub=10.0)
        cons = Constraint(lhs=var, sense="<=", rhs=5.0)
        cons.name = "bn_con"
        cs = ConstraintSensitivity(
            constraint=cons,
            name="bn_con",
            shadow_price=None,
            slack=0.0,
            is_binding=True,
            group=None,
        )
        report = SensitivityReport(
            objective_value=5.0,
            has_duals=False,
            constraints=[cs],
            variables=[],
        )
        result = report.bottlenecks(top_n=5)
        assert len(result) == 1
        assert result[0].name == "bn_con"


# ---------------------------------------------------------------------------
# quality/explainability.py gaps
# ---------------------------------------------------------------------------

class TestExplainabilityGaps:
    def test_explain_model_with_solved_sets_diagnostics(self):
        """explain_model(model, solved=...) populates solve_diagnostics."""
        from polyhedron.quality.explainability import explain_model

        model = Model("explain-with-solved")

        class SimpleExplEl(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            @maximize()
            def obj(self):
                return self.x

        el = SimpleExplEl("se1")
        model.add_element(el)

        values = {el.x: 5.0}
        solved = _make_solved_model(model, values, 5.0)
        report = explain_model(model, solved=solved)
        assert report.solve_diagnostics is not None
        assert "status" in report.solve_diagnostics

    def test_explain_model_without_solved_no_diagnostics(self):
        """explain_model(model) without solved has None diagnostics."""
        from polyhedron.quality.explainability import explain_model

        model = Model("explain-no-solved")

        class SimpleExplEl2(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            @maximize()
            def obj(self):
                return self.x

        el = SimpleExplEl2("se2")
        model.add_element(el)

        report = explain_model(model)
        assert report.solve_diagnostics is None

    def test_explainability_markdown_includes_solve_diagnostics(self):
        """to_markdown() should include solve diagnostics section when present."""
        from polyhedron.quality.explainability import explain_model

        model = Model("explain-md-with-solved")

        class MdSolvedEl(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            @maximize()
            def obj(self):
                return self.x

        el = MdSolvedEl("ms1")
        model.add_element(el)
        solved = _make_solved_model(model, {el.x: 4.0}, 4.0)
        report = explain_model(model, solved=solved)
        md = report.to_markdown()
        assert "### Solve Diagnostics" in md

    def test_explain_model_counts_equality_constraints(self):
        """Hit equality branch in explain_model constraint counting."""
        from polyhedron.quality.explainability import explain_model

        model = Model("explain-eq")

        class EqEl(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            @maximize()
            def obj(self):
                return self.x

        el = EqEl("eq1")
        model.add_element(el)

        @model.constraint(name="eq_con")
        def eq_con():
            return el.x == 3.0

        report = explain_model(model)
        assert report.constraints.equalities >= 1


# ---------------------------------------------------------------------------
# quality/infeasibility.py gaps
# ---------------------------------------------------------------------------

class TestInfeasibilityGaps:
    def _make_model_with_bound_conflict(self):
        model = Model("infeas-gaps")

        class GapElement(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            def objective_contribution(self):
                return 0

        el = GapElement("gp1")
        model.add_element(el)

        @model.constraint(name="upper_limit")
        def upper_limit():
            return el.x <= 1.0

        @model.constraint(name="lower_demand")
        def lower_demand():
            return el.x >= 2.0

        return model, el

    def test_extract_values_with_solution_instance(self):
        """_extract_values with Solution → returns solution.values (line 68-69)."""
        from polyhedron.quality import debug_infeasibility

        model, el = self._make_model_with_bound_conflict()
        solution = Solution(
            status=SolveStatus.OPTIMAL,
            objective_value=0.0,
            values={el.x: 5.0},
            solver_name="mock",
        )
        report = debug_infeasibility(model, candidate=solution)
        assert report.violated_constraints

    def test_extract_values_with_solved_model(self):
        """_extract_values with SolvedModel → returns solution.values (line 67-68)."""
        from polyhedron.quality import debug_infeasibility

        model, el = self._make_model_with_bound_conflict()
        solved = _make_solved_model(model, {el.x: 5.0}, 0.0)
        report = debug_infeasibility(model, candidate=solved)
        assert report.violated_constraints

    def test_extract_values_with_mapping(self):
        """_extract_values with plain dict Mapping → returns mapping (line 70-72)."""
        from polyhedron.quality import debug_infeasibility

        model, el = self._make_model_with_bound_conflict()
        report = debug_infeasibility(model, candidate={el.x: 5.0})
        assert report.violated_constraints

    def test_extract_values_with_invalid_raises_type_error(self):
        """_extract_values with invalid type → raises TypeError (line 73)."""
        from polyhedron.quality import debug_infeasibility

        model, el = self._make_model_with_bound_conflict()
        with pytest.raises(TypeError):
            debug_infeasibility(model, candidate="invalid_string")

    def test_no_static_conflict_found_path(self):
        """debug_infeasibility on feasible model → 'no_static_conflict_found' (line 133)."""
        from polyhedron.quality import debug_infeasibility

        model = Model("feasible-infeas-check")

        class FeasEl(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)

            def objective_contribution(self):
                return 0

        el = FeasEl("fe1")
        model.add_element(el)

        @model.constraint(name="feasible_con")
        def feasible_con():
            return el.x <= 10.0

        report = debug_infeasibility(model)
        assert any(s.kind == "no_static_conflict_found" for s in report.suspects)

    def test_bound_updates_from_constraint_multi_var_returns_none(self):
        """_bound_updates_from_constraint returns None when len(nonzero) != 1 (line 38)."""
        from polyhedron.quality import debug_infeasibility

        model = Model("multi-var-infeas")

        class MultiElement(Element):
            x = Model.ContinuousVar(min=0.0, max=10.0)
            y = Model.ContinuousVar(min=0.0, max=10.0)

            def objective_contribution(self):
                return 0

        el = MultiElement("mv1")
        model.add_element(el)

        # Multi-variable constraint → _bound_updates_from_constraint returns None → continue (line 94)
        @model.constraint(name="multi_var_con")
        def multi_var_con():
            return el.x + el.y <= 15.0

        report = debug_infeasibility(model)
        # Feasible model → no static conflict found
        assert any(s.kind == "no_static_conflict_found" for s in report.suspects)

    def test_bound_updates_from_constraint_geq_with_pos_coef(self):
        """_bound_updates_from_constraint with >= sense (lines 52-55)."""
        from polyhedron.quality._analysis import constraint_to_standard
        from polyhedron.quality.infeasibility import _bound_updates_from_constraint
        x = _make_var("bu_x", lb=0.0, ub=10.0)
        # x >= 3: in standard form, diff = x - 3, coef={x:1}, constant=-3, sense=">="
        cons = (x >= 3.0)
        view = constraint_to_standard(cons)
        result = _bound_updates_from_constraint(view.coefficients, view.constant, view.sense)
        assert result is not None
        var_out, lower, upper = result
        assert lower == pytest.approx(3.0)

    def test_bound_updates_from_constraint_leq_negative_coef(self):
        """_bound_updates_from_constraint <= with negative coef (line 51)."""
        from polyhedron.quality._analysis import constraint_to_standard
        from polyhedron.quality.infeasibility import _bound_updates_from_constraint
        x = _make_var("bu_neg", lb=0.0, ub=10.0)
        # -x <= -2 means x >= 2: in standard form, diff = -x - (-2) = -x + 2
        # but constraint (-1)*x <= -2 → coef={x:-1}, constant=2-0=2? Let's do it differently:
        # Use a Constraint directly: lhs = -x (Expression with coef -1), rhs = -2
        from polyhedron.core.expression import Expression
        neg_x = Expression([(x, -1.0)])
        cons = Constraint(lhs=neg_x, sense="<=", rhs=-2.0)
        view = constraint_to_standard(cons)
        result = _bound_updates_from_constraint(view.coefficients, view.constant, view.sense)
        assert result is not None

    def test_bound_updates_from_constraint_eq_sense(self):
        """_bound_updates_from_constraint with == sense (lines 57-59)."""
        from polyhedron.quality._analysis import constraint_to_standard
        from polyhedron.quality.infeasibility import _bound_updates_from_constraint
        x = _make_var("bu_eq", lb=0.0, ub=10.0)
        cons = (x == 5.0)
        view = constraint_to_standard(cons)
        result = _bound_updates_from_constraint(view.coefficients, view.constant, view.sense)
        assert result is not None
        var_out, lower, upper = result
        assert lower == pytest.approx(5.0)
        assert upper == pytest.approx(5.0)

    def test_bound_updates_from_constraint_unknown_sense(self):
        """_bound_updates_from_constraint with unknown sense returns None (line 61)."""
        from polyhedron.quality.infeasibility import _bound_updates_from_constraint
        x = _make_var("bu_unk", lb=0.0, ub=10.0)
        result = _bound_updates_from_constraint({x: 1.0}, constant=-5.0, sense="~=")
        assert result is None

    def test_bound_updates_from_constraint_geq_negative_coef_sets_upper(self):
        """Cover >= branch with negative coefficient (upper = rhs)."""
        from polyhedron.quality.infeasibility import _bound_updates_from_constraint

        x = _make_var("bu_geq_neg", lb=0.0, ub=10.0)
        result = _bound_updates_from_constraint({x: -2.0}, constant=4.0, sense=">=")
        assert result is not None
        _var, lower, upper = result
        assert lower == float("-inf")
        assert upper == pytest.approx(2.0)
