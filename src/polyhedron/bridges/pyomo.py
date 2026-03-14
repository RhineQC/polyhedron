from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Any, Dict, Mapping, Optional

from polyhedron import Model
from polyhedron.backends.compiler import combine_expressions, compile_model
from polyhedron.core.constraint import Constraint
from polyhedron.core.expression import Expression
from polyhedron.core.variable import VarType, Variable, VariableDefinition
from polyhedron.modeling.element import Element


@dataclass(frozen=True)
class PyomoToPolyhedronConversionResult:
    model: Model
    polyhedron_variables: Dict[str, Variable]
    pyomo_variables: Dict[str, Any]


@dataclass(frozen=True)
class PolyhedronToPyomoConversionResult:
    pyomo_model: Any
    polyhedron_variables: Dict[str, Variable]
    pyomo_variables: Dict[str, Any]


def _require_pyomo():
    try:
        from pyomo.environ import Constraint as PyomoConstraint
        from pyomo.environ import Objective as PyomoObjective
        from pyomo.environ import Var as PyomoVar
        from pyomo.environ import Binary, ConcreteModel, Integers, Reals, maximize, minimize, value
        from pyomo.repn import generate_standard_repn
    except Exception as exc:  # noqa: BLE001
        raise ImportError("Pyomo is required for conversion. Install optional dependency 'pyomo'.") from exc

    return {
        "Binary": Binary,
        "ConcreteModel": ConcreteModel,
        "Constraint": PyomoConstraint,
        "Integers": Integers,
        "Objective": PyomoObjective,
        "Reals": Reals,
        "Var": PyomoVar,
        "maximize": maximize,
        "minimize": minimize,
        "value": value,
        "generate_standard_repn": generate_standard_repn,
    }


def _var_type_and_bounds(pyomo_var: Any) -> tuple[VarType, float, float]:
    if pyomo_var.is_binary():
        return (VarType.BINARY, 0.0, 1.0)
    if pyomo_var.is_integer():
        lower = float(pyomo_var.lb) if pyomo_var.lb is not None else float("-inf")
        upper = float(pyomo_var.ub) if pyomo_var.ub is not None else float("inf")
        return (VarType.INTEGER, lower, upper)
    lower = float(pyomo_var.lb) if pyomo_var.lb is not None else float("-inf")
    upper = float(pyomo_var.ub) if pyomo_var.ub is not None else float("inf")
    return (VarType.CONTINUOUS, lower, upper)


def _make_bridge_element_class(var_defs: Dict[str, VariableDefinition]):
    def objective_contribution(self):
        return getattr(self, "_objective_expr", 0.0)

    attrs: Dict[str, object] = {"objective_contribution": objective_contribution}
    attrs.update(var_defs)
    return type("PyomoBridgeElement", (Element,), attrs)


def _to_expression(value: object) -> Expression:
    if isinstance(value, Expression):
        return value
    if isinstance(value, Variable):
        return Expression([(value, 1.0)])
    if isinstance(value, (int, float)):
        return Expression(constant=float(value))
    raise TypeError(f"Unsupported operand type for conversion: {type(value)}")


def _convert_linear_expression(expr: Any, var_map: Mapping[int, Variable], generate_standard_repn: Any) -> Expression:
    repn = generate_standard_repn(expr, compute_values=True)
    if not repn.is_linear() or repn.nonlinear_expr is not None:
        raise ValueError("Only linear Pyomo expressions are currently supported by convert_pyomo_model().")
    if getattr(repn, "quadratic_vars", None):
        raise ValueError("Quadratic Pyomo expressions are not supported by convert_pyomo_model().")

    terms = []
    for pyomo_var, coef in zip(repn.linear_vars, repn.linear_coefs):
        key = id(pyomo_var)
        if key not in var_map:
            raise ValueError(f"Expression references unknown Pyomo variable: {pyomo_var}")
        terms.append((var_map[key], float(coef)))

    return Expression(terms=terms, constant=float(repn.constant or 0.0))


def convert_pyomo_model(
    pyomo_model: Any,
    *,
    model_name: Optional[str] = None,
    solver: str = "scip",
) -> PyomoToPolyhedronConversionResult:
    pyomo = _require_pyomo()
    PyomoVar = pyomo["Var"]
    PyomoConstraint = pyomo["Constraint"]
    PyomoObjective = pyomo["Objective"]
    minimize = pyomo["minimize"]
    value = pyomo["value"]
    generate_standard_repn = pyomo["generate_standard_repn"]

    pyomo_vars = list(pyomo_model.component_data_objects(PyomoVar, active=True))

    var_defs: Dict[str, VariableDefinition] = {}
    pyomo_name_by_attr: Dict[str, str] = {}
    pyomo_var_by_attr: Dict[str, Any] = {}
    for idx, pyomo_var in enumerate(pyomo_vars):
        attr = f"v_{idx}"
        pyomo_name = str(getattr(pyomo_var, "_polyhedron_name", str(pyomo_var.name)))
        var_type, lower, upper = _var_type_and_bounds(pyomo_var)
        var_defs[attr] = VariableDefinition(var_type, lower, upper)
        pyomo_name_by_attr[attr] = pyomo_name
        pyomo_var_by_attr[attr] = pyomo_var

    BridgeElement = _make_bridge_element_class(var_defs)
    bridge_element = BridgeElement("pyomo_bridge", _objective_expr=0.0)

    model = Model(model_name or getattr(pyomo_model, "name", "pyomo_converted"), solver=solver)
    model.add_element(bridge_element)

    poly_vars_by_pyomo_name: Dict[str, Variable] = {}
    pyomo_vars_by_name: Dict[str, Any] = {}
    var_map_by_id: Dict[int, Variable] = {}
    pyomo_name_by_polyhedron_name: Dict[str, str] = {}

    for attr, pyomo_name in pyomo_name_by_attr.items():
        poly_var = bridge_element.variables[attr]
        poly_vars_by_pyomo_name[pyomo_name] = poly_var
        pyomo_var = pyomo_var_by_attr[attr]
        pyomo_vars_by_name[pyomo_name] = pyomo_var
        var_map_by_id[id(pyomo_var)] = poly_var
        pyomo_name_by_polyhedron_name[poly_var.name] = pyomo_name

    objectives = list(pyomo_model.component_data_objects(PyomoObjective, active=True))
    if len(objectives) > 1:
        raise ValueError(
            "Only one active Pyomo objective is supported for conversion. "
            "Flatten multiple objectives into a single weighted objective before converting."
        )

    if objectives:
        objective = objectives[0]
        bridge_element._objective_expr = _convert_linear_expression(
            objective.expr,
            var_map_by_id,
            generate_standard_repn,
        )
        model.objective_sense = "minimize" if objective.sense == minimize else "maximize"

    for constraint in pyomo_model.component_data_objects(PyomoConstraint, active=True):
        body = _convert_linear_expression(constraint.body, var_map_by_id, generate_standard_repn)

        lower = float(value(constraint.lower)) if constraint.has_lb() else None
        upper = float(value(constraint.upper)) if constraint.has_ub() else None
        base_name = str(constraint.name)

        if lower is not None and upper is not None and isclose(lower, upper, abs_tol=1e-12):
            cons = body == lower
            cons.name = base_name
            model.constraints.append(cons)
            continue

        if lower is not None:
            cons = body >= lower
            cons.name = f"{base_name}:lb"
            model.constraints.append(cons)

        if upper is not None:
            cons = body <= upper
            cons.name = f"{base_name}:ub"
            model.constraints.append(cons)

    # Persist preferred external naming for follow-up Polyhedron -> Pyomo conversion.
    setattr(model, "_pyomo_name_by_polyhedron_name", pyomo_name_by_polyhedron_name)

    return PyomoToPolyhedronConversionResult(
        model=model,
        polyhedron_variables=poly_vars_by_pyomo_name,
        pyomo_variables=pyomo_vars_by_name,
    )


def apply_polyhedron_values_to_pyomo(
    conversion: PyomoToPolyhedronConversionResult,
    values: Mapping[Variable, float],
) -> None:
    for pyomo_name, poly_var in conversion.polyhedron_variables.items():
        if poly_var not in values:
            continue
        conversion.pyomo_variables[pyomo_name].set_value(float(values[poly_var]))


def _var_domain(var: Variable, pyomo: Mapping[str, Any]) -> Any:
    if var.var_type == VarType.BINARY:
        return pyomo["Binary"]
    if var.var_type == VarType.INTEGER:
        return pyomo["Integers"]
    return pyomo["Reals"]


def _expression_to_pyomo(expr: Expression, pyomo_var_by_name: Mapping[str, Any]) -> Any:
    result = float(expr.constant)
    for var, coef in expr.terms:
        if var.name not in pyomo_var_by_name:
            raise ValueError(f"Missing mapped Pyomo variable for '{var.name}'.")
        result = result + float(coef) * pyomo_var_by_name[var.name]
    return result


def convert_polyhedron_model(model: Model) -> PolyhedronToPyomoConversionResult:
    pyomo = _require_pyomo()
    ConcreteModel = pyomo["ConcreteModel"]
    PyomoVar = pyomo["Var"]
    PyomoConstraint = pyomo["Constraint"]
    PyomoObjective = pyomo["Objective"]
    minimize = pyomo["minimize"]
    maximize = pyomo["maximize"]

    compiled = compile_model(model)
    pyomo_model = ConcreteModel()
    preferred_name_by_poly_name = getattr(model, "_pyomo_name_by_polyhedron_name", {})

    pyomo_variables: Dict[str, Any] = {}
    polyhedron_variables: Dict[str, Variable] = {}
    pyomo_variables_by_internal_name: Dict[str, Any] = {}
    used_export_names: Dict[str, str] = {}

    for idx, var in enumerate(compiled.variables):
        component_name = f"v_{idx}"
        export_name = preferred_name_by_poly_name.get(var.name, var.name)
        if export_name in used_export_names and used_export_names[export_name] != var.name:
            raise ValueError(
                "Cannot export Polyhedron model to Pyomo: duplicate external variable name "
                f"'{export_name}' from '{used_export_names[export_name]}' and '{var.name}'."
            )
        used_export_names[export_name] = var.name
        kwargs: Dict[str, object] = {"domain": _var_domain(var, pyomo)}
        lb = None if var.lower_bound == float("-inf") else float(var.lower_bound)
        ub = None if var.upper_bound == float("inf") else float(var.upper_bound)
        if lb is not None or ub is not None:
            kwargs["bounds"] = (lb, ub)
        py_var = PyomoVar(**kwargs)
        pyomo_model.add_component(component_name, py_var)
        setattr(py_var, "_polyhedron_name", export_name)
        pyomo_variables[export_name] = py_var
        polyhedron_variables[export_name] = var
        pyomo_variables_by_internal_name[var.name] = py_var

    objective_expr = combine_expressions(compiled.objective_terms)
    if objective_expr is not None:
        objective_linear = _to_expression(objective_expr)
        pyomo_obj_expr = _expression_to_pyomo(objective_linear, pyomo_variables_by_internal_name)
        sense = minimize if compiled.objective_sense == "minimize" else maximize
        pyomo_model.add_component("obj", PyomoObjective(expr=pyomo_obj_expr, sense=sense))

    for idx, cons in enumerate(compiled.constraints):
        lhs = _to_expression(cons.lhs)
        rhs = _to_expression(cons.rhs)
        diff = lhs - rhs
        pyomo_expr = _expression_to_pyomo(diff, pyomo_variables_by_internal_name)
        name = cons.name or f"c_{idx}"
        if cons.sense == "==":
            component = PyomoConstraint(expr=pyomo_expr == 0)
        elif cons.sense == "<=":
            component = PyomoConstraint(expr=pyomo_expr <= 0)
        elif cons.sense == ">=":
            component = PyomoConstraint(expr=pyomo_expr >= 0)
        else:
            raise ValueError(f"Unsupported constraint sense: {cons.sense}")
        pyomo_model.add_component(f"con_{idx}_{name.replace(':', '_')}", component)

    return PolyhedronToPyomoConversionResult(
        pyomo_model=pyomo_model,
        polyhedron_variables=polyhedron_variables,
        pyomo_variables=pyomo_variables,
    )


def apply_pyomo_values_to_polyhedron(
    conversion: PolyhedronToPyomoConversionResult,
) -> Dict[Variable, float]:
    pyomo = _require_pyomo()
    value = pyomo["value"]
    result: Dict[Variable, float] = {}
    for var_name, poly_var in conversion.polyhedron_variables.items():
        py_var = conversion.pyomo_variables[var_name]
        var_value = value(py_var, exception=False)
        if var_value is None:
            continue
        result[poly_var] = float(var_value)
    return result
