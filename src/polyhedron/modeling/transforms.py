from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression, QuadraticExpression, QuadraticTerm, expression_bounds
from polyhedron.core.variable import Variable, VarType


def _as_expression(value) -> Expression | QuadraticExpression:
    if isinstance(value, QuadraticExpression):
        return value
    if isinstance(value, Expression):
        return value
    if isinstance(value, QuadraticTerm):
        return QuadraticExpression(quadratic_terms=[value])
    if isinstance(value, Variable):
        return Expression([(value, 1.0)])
    return Expression(constant=float(value))


def _big_m_for_constraint(constraint: Constraint) -> float:
    lhs_lower, lhs_upper = expression_bounds(constraint.lhs)
    rhs_lower, rhs_upper = expression_bounds(constraint.rhs)
    if constraint.sense == "<=":
        return max(0.0, lhs_upper - rhs_lower)
    if constraint.sense == ">=":
        return max(0.0, rhs_upper - lhs_lower)
    return max(abs(lhs_upper - rhs_lower), abs(rhs_upper - lhs_lower), abs(lhs_lower - rhs_upper), abs(rhs_lower - lhs_upper))


@dataclass(frozen=True)
class PiecewiseLinearResult:
    output: Variable
    lambdas: Sequence[Variable]
    selectors: Sequence[Variable]
    constraints: Sequence[Constraint]


def abs_var(model, expr, *, name: str, upper_bound: float | None = None) -> Variable:
    lower, upper = expression_bounds(expr)
    magnitude = max(abs(lower), abs(upper)) if upper_bound is None else float(upper_bound)
    output = model.add_variable(name, lower_bound=0.0, upper_bound=max(magnitude, 0.0))
    model.constraints.append(Constraint(lhs=output, sense=">=", rhs=_as_expression(expr), name=f"{name}:abs_pos"))
    model.constraints.append(Constraint(lhs=output, sense=">=", rhs=-_as_expression(expr), name=f"{name}:abs_neg"))
    return output


def max_var(model, expressions: Iterable[object], *, name: str) -> Variable:
    items = list(expressions)
    if not items:
        raise ValueError("max_var requires at least one expression.")
    lowers, uppers = zip(*(expression_bounds(expr) for expr in items))
    output = model.add_variable(name, lower_bound=max(lowers), upper_bound=max(uppers))
    selectors = model.var_array(f"{name}_selector", model.index_set(f"{name}_selector_idx", range(len(items))), var_type=VarType.BINARY)
    model.constraints.append(Constraint(lhs=selectors.sum(), sense="==", rhs=1, name=f"{name}:choose_one"))
    for idx, expr in enumerate(items):
        lower, upper = expression_bounds(expr)
        model.constraints.append(Constraint(lhs=output, sense=">=", rhs=_as_expression(expr), name=f"{name}:lb:{idx}"))
        model.constraints.append(
            Constraint(
                lhs=output,
                sense="<=",
                rhs=_as_expression(expr) + max(0.0, max(uppers) - lower) * (1 - selectors[idx]),
                name=f"{name}:ub:{idx}",
            )
        )
    return output


def min_var(model, expressions: Iterable[object], *, name: str) -> Variable:
    items = list(expressions)
    if not items:
        raise ValueError("min_var requires at least one expression.")
    lowers, uppers = zip(*(expression_bounds(expr) for expr in items))
    output = model.add_variable(name, lower_bound=min(lowers), upper_bound=min(uppers))
    selectors = model.var_array(f"{name}_selector", model.index_set(f"{name}_selector_idx", range(len(items))), var_type=VarType.BINARY)
    model.constraints.append(Constraint(lhs=selectors.sum(), sense="==", rhs=1, name=f"{name}:choose_one"))
    for idx, expr in enumerate(items):
        _lower, upper = expression_bounds(expr)
        model.constraints.append(Constraint(lhs=output, sense="<=", rhs=_as_expression(expr), name=f"{name}:ub:{idx}"))
        model.constraints.append(
            Constraint(
                lhs=output,
                sense=">=",
                rhs=_as_expression(expr) - max(0.0, upper - min(lowers)) * (1 - selectors[idx]),
                name=f"{name}:lb:{idx}",
            )
        )
    return output


def indicator(model, binary: Variable, constraint: Constraint, *, name: str, active_value: int = 1, big_m: float | None = None) -> list[Constraint]:
    if binary.var_type != VarType.BINARY:
        raise TypeError("indicator requires a binary control variable.")
    if active_value not in {0, 1}:
        raise ValueError("active_value must be 0 or 1.")
    bound = float(big_m) if big_m is not None else max(_big_m_for_constraint(constraint), 1.0)
    trigger = binary if active_value == 1 else 1 - binary
    if constraint.sense == "<=":
        linearized = Constraint(lhs=constraint.lhs, sense="<=", rhs=_as_expression(constraint.rhs) + bound * (1 - trigger), name=name, group=constraint.group, tags=constraint.tags)
        model.constraints.append(linearized)
        return [linearized]
    if constraint.sense == ">=":
        linearized = Constraint(lhs=constraint.lhs, sense=">=", rhs=_as_expression(constraint.rhs) - bound * (1 - trigger), name=name, group=constraint.group, tags=constraint.tags)
        model.constraints.append(linearized)
        return [linearized]
    left = Constraint(lhs=constraint.lhs, sense="<=", rhs=_as_expression(constraint.rhs) + bound * (1 - trigger), name=f"{name}:upper")
    right = Constraint(lhs=constraint.lhs, sense=">=", rhs=_as_expression(constraint.rhs) - bound * (1 - trigger), name=f"{name}:lower")
    model.constraints.extend([left, right])
    return [left, right]


def add_sos1(model, variables: Sequence[Variable], *, name: str) -> list[Constraint]:
    if not variables:
        return []
    selector = model.var_array(f"{name}_select", model.index_set(f"{name}_select_idx", range(len(variables))), var_type=VarType.BINARY)
    constraints = [Constraint(lhs=selector.sum(), sense="<=", rhs=1, name=f"{name}:choose")]
    for idx, var in enumerate(variables):
        bound = max(abs(var.lower_bound), abs(var.upper_bound if var.upper_bound != float("inf") else 1_000_000.0), 1.0)
        constraints.append(Constraint(lhs=var, sense="<=", rhs=bound * selector[idx], name=f"{name}:ub:{idx}"))
        constraints.append(Constraint(lhs=var, sense=">=", rhs=-bound * selector[idx], name=f"{name}:lb:{idx}"))
    model.constraints.extend(constraints)
    return constraints


def add_sos2(model, lambdas: Sequence[Variable], *, name: str) -> list[Constraint]:
    if len(lambdas) < 2:
        raise ValueError("add_sos2 requires at least two variables.")
    segments = model.var_array(f"{name}_segment", model.index_set(f"{name}_segment_idx", range(len(lambdas) - 1)), var_type=VarType.BINARY)
    constraints = [Constraint(lhs=segments.sum(), sense="==", rhs=1, name=f"{name}:segment_choice")]
    for idx, lam in enumerate(lambdas):
        neighbors = []
        if idx > 0:
            neighbors.append(segments[idx - 1])
        if idx < len(lambdas) - 1:
            neighbors.append(segments[idx])
        constraints.append(Constraint(lhs=lam, sense="<=", rhs=sum(neighbors, 0.0), name=f"{name}:adjacent:{idx}"))
    model.constraints.extend(constraints)
    return constraints


def piecewise_linear(
    model,
    *,
    name: str,
    input_var: Variable,
    breakpoints: Sequence[float],
    values: Sequence[float],
) -> PiecewiseLinearResult:
    if len(breakpoints) != len(values):
        raise ValueError("breakpoints and values must have identical length.")
    if len(breakpoints) < 2:
        raise ValueError("piecewise_linear requires at least two breakpoints.")
    output = model.add_variable(name, lower_bound=min(values), upper_bound=max(values))
    lam = model.var_array(f"{name}_lambda", model.index_set(f"{name}_lambda_idx", range(len(breakpoints))), lower_bound=0.0, upper_bound=1.0)
    constraints = [
        Constraint(lhs=lam.sum(), sense="==", rhs=1, name=f"{name}:convex_sum"),
        Constraint(lhs=input_var, sense="==", rhs=sum(bp * lam[idx] for idx, bp in enumerate(breakpoints)), name=f"{name}:x_link"),
        Constraint(lhs=output, sense="==", rhs=sum(val * lam[idx] for idx, val in enumerate(values)), name=f"{name}:y_link"),
    ]
    model.constraints.extend(constraints)
    selectors = model.var_array(f"{name}_sos2", model.index_set(f"{name}_sos2_idx", range(len(breakpoints) - 1)), var_type=VarType.BINARY)
    model.constraints.append(Constraint(lhs=selectors.sum(), sense="==", rhs=1, name=f"{name}:segment_sum"))
    constraints.extend(add_sos2(model, [lam[idx] for idx in range(len(breakpoints))], name=f"{name}:sos2"))
    return PiecewiseLinearResult(output=output, lambdas=lam.values(), selectors=selectors.values(), constraints=constraints)


def piecewise_cost(model, *, name: str, input_var: Variable, breakpoints: Sequence[float], costs: Sequence[float]) -> Variable:
    return piecewise_linear(model, name=name, input_var=input_var, breakpoints=breakpoints, values=costs).output


def disjunction(model, groups: Sequence[Sequence[Constraint]], *, name: str, big_m: float | None = None) -> tuple[Variable, ...]:
    selectors = model.var_array(f"{name}_disj", model.index_set(f"{name}_disj_idx", range(len(groups))), var_type=VarType.BINARY)
    model.constraints.append(Constraint(lhs=selectors.sum(), sense="==", rhs=1, name=f"{name}:pick"))
    for idx, group in enumerate(groups):
        for offset, constraint in enumerate(group):
            indicator(model, selectors[idx], constraint, name=f"{name}:{idx}:{offset}", active_value=1, big_m=big_m)
    return selectors.values()


__all__ = [
    "PiecewiseLinearResult",
    "abs_var",
    "max_var",
    "min_var",
    "indicator",
    "add_sos1",
    "add_sos2",
    "piecewise_linear",
    "piecewise_cost",
    "disjunction",
]