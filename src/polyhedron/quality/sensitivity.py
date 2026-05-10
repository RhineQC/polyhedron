from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.solution import SolvedModel
from polyhedron.core.variable import Variable, VarType
from polyhedron.quality._analysis import constraint_to_standard, evaluate_expression, to_expression


@dataclass(frozen=True)
class ConstraintSensitivity:
    """Sensitivity information for a single constraint after solving.

    Attributes:
        constraint: The original constraint object.
        name: Human-readable name (falls back to group or index key).
        shadow_price: Change in objective value per unit increase in the RHS.
            Positive means relaxing this constraint improves the objective.
            Only available for LP relaxations; ``None`` for MIP solves.
        slack: Distance from the constraint boundary. Zero means the
            constraint is exactly binding at the optimal solution.
        is_binding: ``True`` when slack is at or below *tolerance*.
        group: Constraint group tag if set on the original constraint.
    """

    constraint: Constraint
    name: str
    shadow_price: Optional[float]
    slack: float
    is_binding: bool
    group: Optional[str]

    @property
    def opportunity_cost(self) -> Optional[float]:
        """Alias for *shadow_price* using financial terminology."""
        return self.shadow_price

    @property
    def marginal_value(self) -> Optional[float]:
        """Absolute value of shadow price — how much one more unit is worth."""
        return abs(self.shadow_price) if self.shadow_price is not None else None


@dataclass(frozen=True)
class VariableSensitivity:
    """Sensitivity information for a single decision variable after solving.

    Attributes:
        variable: The original variable object.
        value: Optimal value in the solution.
        reduced_cost: Change in objective if this variable is forced away from
            its current bound by one unit. Only available for LP relaxations.
        is_at_lower_bound: ``True`` when the value equals the lower bound.
        is_at_upper_bound: ``True`` when the value equals the upper bound.
        is_basic: ``True`` when the variable is strictly between its bounds
            (neither bound is active).
    """

    variable: Variable
    value: float
    reduced_cost: Optional[float]
    is_at_lower_bound: bool
    is_at_upper_bound: bool

    @property
    def is_basic(self) -> bool:
        return not self.is_at_lower_bound and not self.is_at_upper_bound

    @property
    def active_bound(self) -> Optional[str]:
        if self.is_at_lower_bound:
            return "lower"
        if self.is_at_upper_bound:
            return "upper"
        return None


@dataclass(frozen=True)
class SensitivityReport:
    """Full sensitivity analysis of a solved model.

    Constructed via :func:`sensitivity`. All constraint and variable lists are
    sorted by descending impact (binding constraints first, highest shadow
    prices first within each group).

    Attributes:
        objective_value: Optimal objective value.
        has_duals: Whether dual/shadow-price information is available.
            MIP solvers typically do not provide duals.
        constraints: All constraints with sensitivity data.
        variables: All decision variables with sensitivity data.
    """

    objective_value: Optional[float]
    has_duals: bool
    constraints: List[ConstraintSensitivity] = field(default_factory=list)
    variables: List[VariableSensitivity] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Constraint views
    # ------------------------------------------------------------------

    @property
    def binding_constraints(self) -> List[ConstraintSensitivity]:
        """Constraints that are exactly active (slack ≈ 0) at the optimum."""
        return [c for c in self.constraints if c.is_binding]

    @property
    def nonbinding_constraints(self) -> List[ConstraintSensitivity]:
        """Constraints with positive slack — they are not limiting the solution."""
        return [c for c in self.constraints if not c.is_binding]

    def bottlenecks(self, top_n: int = 10) -> List[ConstraintSensitivity]:
        """Binding constraints ranked by descending absolute shadow_price.

        These are the constraints most worth relaxing to improve the objective.
        If dual information is unavailable, returns binding constraints sorted
        by name.
        """
        binding = self.binding_constraints
        if self.has_duals:
            return sorted(
                binding,
                key=lambda c: abs(c.shadow_price or 0.0),
                reverse=True,
            )[:top_n]
        return binding[:top_n]

    def by_group(self, group: str) -> List[ConstraintSensitivity]:
        """All constraint sensitivities belonging to a named group."""
        return [c for c in self.constraints if c.group == group]

    # ------------------------------------------------------------------
    # Variable views
    # ------------------------------------------------------------------

    @property
    def variables_at_bound(self) -> List[VariableSensitivity]:
        """Variables pinned against a bound — potential candidates for relaxation."""
        return [v for v in self.variables if not v.is_basic]

    def most_constrained_variables(self, top_n: int = 10) -> List[VariableSensitivity]:
        """Non-basic variables ranked by descending absolute reduced_cost."""
        at_bound = self.variables_at_bound
        if self.has_duals:
            return sorted(
                at_bound,
                key=lambda v: abs(v.reduced_cost or 0.0),
                reverse=True,
            )[:top_n]
        return at_bound[:top_n]

    # ------------------------------------------------------------------
    # Narrative output
    # ------------------------------------------------------------------

    def summary(self, top_n: int = 5) -> str:
        """Return a human-readable text summary of the sensitivity analysis."""
        lines: List[str] = []
        lines.append("=== Sensitivity Analysis ===")
        lines.append(f"Objective value : {self.objective_value}")
        lines.append(f"Dual info       : {'available' if self.has_duals else 'not available (MIP solve)'}")
        lines.append(f"Constraints     : {len(self.constraints)} total, {len(self.binding_constraints)} binding")
        lines.append(f"Variables       : {len(self.variables)} total, {len(self.variables_at_bound)} at bound")
        lines.append("")

        top = self.bottlenecks(top_n)
        if top:
            lines.append(f"Top {len(top)} bottleneck constraint(s):")
            for cs in top:
                price_str = (
                    f"shadow price = {cs.shadow_price:+.4g}"
                    if cs.shadow_price is not None
                    else "shadow price = n/a"
                )
                lines.append(f"  [{cs.group or 'ungrouped'}] {cs.name}  (slack={cs.slack:.4g}, {price_str})")
        else:
            lines.append("No binding constraints detected.")

        if self.has_duals:
            lines.append("")
            top_vars = self.most_constrained_variables(top_n)
            if top_vars:
                lines.append(f"Top {len(top_vars)} most constrained variable(s):")
                for vs in top_vars:
                    lines.append(
                        f"  {vs.variable.name} = {vs.value:.4g}  "
                        f"(bound={vs.active_bound}, reduced cost={vs.reduced_cost:+.4g})"
                    )

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Return a GitHub-flavoured Markdown sensitivity report."""
        lines: List[str] = []
        lines.append("## Sensitivity Analysis")
        lines.append("")
        lines.append(f"**Objective value:** `{self.objective_value}`  ")
        lines.append(
            f"**Dual/shadow-price info:** {'available' if self.has_duals else 'not available (MIP solve)'}"
        )
        lines.append("")

        lines.append("### Binding Constraints")
        binding = self.binding_constraints
        if binding:
            lines.append("")
            lines.append("| Name | Group | Shadow Price | Slack |")
            lines.append("|------|-------|-------------|-------|")
            for cs in sorted(binding, key=lambda c: abs(c.shadow_price or 0.0), reverse=True):
                sp = f"{cs.shadow_price:+.4g}" if cs.shadow_price is not None else "n/a"
                lines.append(f"| {cs.name} | {cs.group or ''} | {sp} | {cs.slack:.4g} |")
        else:
            lines.append("_No binding constraints._")

        lines.append("")
        lines.append("### Variables at Bound")
        at_bound = self.variables_at_bound
        if at_bound:
            lines.append("")
            lines.append("| Variable | Value | Bound | Reduced Cost |")
            lines.append("|----------|-------|-------|--------------|")
            for vs in sorted(at_bound, key=lambda v: abs(v.reduced_cost or 0.0), reverse=True):
                rc = f"{vs.reduced_cost:+.4g}" if vs.reduced_cost is not None else "n/a"
                lines.append(f"| {vs.variable.name} | {vs.value:.4g} | {vs.active_bound} | {rc} |")
        else:
            lines.append("_No variables at bound._")

        return "\n".join(lines)


def sensitivity(
    solved: SolvedModel,
    *,
    binding_tolerance: float = 1e-6,
) -> SensitivityReport:
    """Compute a :class:`SensitivityReport` from a solved model.

    Requires the solver to have been run in LP mode (or LP relaxation) to
    obtain shadow prices and reduced costs. For MIP solves the report is still
    useful: it identifies which constraints are binding and which variables are
    at their bounds, but dual values will be absent.

    Args:
        solved: A :class:`~polyhedron.core.solution.SolvedModel` returned by
            ``model.solve()``.
        binding_tolerance: Slack values below this threshold are treated as
            zero (constraint is binding). Default ``1e-6``.

    Returns:
        A :class:`SensitivityReport` with constraint and variable sensitivity
        data.

    Example::

        from polyhedron import sensitivity

        solved = model.solve()
        report = sensitivity(solved)
        print(report.summary())
        print(report.to_markdown())

        # Inspect bottleneck constraints
        for cs in report.bottlenecks(top_n=3):
            print(cs.name, cs.shadow_price, cs.slack)
    """
    sol = solved.solution
    values = sol.values
    duals = sol.constraint_duals or {}
    slacks = sol.constraint_slacks or {}
    red_costs = sol.reduced_costs or {}
    has_duals = bool(duals or red_costs)

    from polyhedron.core.model import Model
    model = solved.model
    if not isinstance(model, Model):
        raise TypeError("solved.model must be a polyhedron Model")

    from polyhedron.backends.compiler import compile_model
    compiled = compile_model(model)

    constraint_sensitivities: List[ConstraintSensitivity] = []
    for cons in compiled.constraints:
        shadow = duals.get(cons)
        raw_slack = slacks.get(cons)

        if raw_slack is None:
            # Compute slack ourselves from variable values
            view = constraint_to_standard(cons)
            expr = to_expression(cons.lhs) - to_expression(cons.rhs)
            lhs_val = evaluate_expression(to_expression(cons.lhs), values)
            rhs_val = evaluate_expression(to_expression(cons.rhs), values)
            if cons.sense == "<=":
                raw_slack = rhs_val - lhs_val
            elif cons.sense == ">=":
                raw_slack = lhs_val - rhs_val
            else:  # ==
                raw_slack = abs(lhs_val - rhs_val)

        slack = max(0.0, float(raw_slack))
        is_binding = slack <= binding_tolerance

        label = (
            cons.name
            or (f"{cons.group}[{cons.index_key}]" if cons.group and cons.index_key is not None else None)
            or (cons.group or "<unnamed>")
        )

        constraint_sensitivities.append(
            ConstraintSensitivity(
                constraint=cons,
                name=label,
                shadow_price=float(shadow) if shadow is not None else None,
                slack=slack,
                is_binding=is_binding,
                group=cons.group,
            )
        )

    # Sort: binding first, then by |shadow_price| desc
    constraint_sensitivities.sort(
        key=lambda c: (not c.is_binding, -abs(c.shadow_price or 0.0))
    )

    variable_sensitivities: List[VariableSensitivity] = []
    for var in compiled.variables:
        val = float(values.get(var, 0.0))
        rc = red_costs.get(var)
        lb = var.lower_bound if var.lower_bound is not None else float("-inf")
        ub = var.upper_bound if var.upper_bound is not None else float("inf")
        at_lower = abs(val - lb) <= binding_tolerance if lb != float("-inf") else False
        at_upper = abs(val - ub) <= binding_tolerance if ub != float("inf") else False

        variable_sensitivities.append(
            VariableSensitivity(
                variable=var,
                value=val,
                reduced_cost=float(rc) if rc is not None else None,
                is_at_lower_bound=at_lower,
                is_at_upper_bound=at_upper,
            )
        )

    variable_sensitivities.sort(
        key=lambda v: (v.is_basic, -abs(v.reduced_cost or 0.0))
    )

    return SensitivityReport(
        objective_value=sol.objective_value,
        has_duals=has_duals,
        constraints=constraint_sensitivities,
        variables=variable_sensitivities,
    )
