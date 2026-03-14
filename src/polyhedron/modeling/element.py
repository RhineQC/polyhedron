from __future__ import annotations

from typing import Dict, List, Optional

from polyhedron.contracts.runtime import validate_element_kwargs
from polyhedron.core.constraint import Constraint
from polyhedron.core.objective import Objective, iter_objective_methods, normalize_objective_sense
from polyhedron.core.variable import VariableDefinition


class Element:
    _model: Optional["Model"] = None

    def __init__(self, name: str, **kwargs):
        self.name = name
        self._variables: Dict[str, object] = {}
        self._constraints: List[Constraint] = []

        kwargs = validate_element_kwargs(self.__class__, kwargs)
        for key, value in kwargs.items():
            setattr(self, key, value)

        self._create_variables()
        self._generate_auto_constraints()

    @property
    def variables(self) -> Dict[str, object]:
        return self._variables

    @property
    def constraints(self) -> List[Constraint]:
        return self._constraints

    def _create_variables(self) -> None:
        for attr_name in dir(self.__class__):
            attr = getattr(self.__class__, attr_name)
            if isinstance(attr, VariableDefinition):
                var = attr.create_variable(f"{self.name}_{attr_name}")
                self._variables[attr_name] = var
                setattr(self, attr_name, var)

    def _generate_auto_constraints(self) -> None:
        for attr_name in dir(self):
            method = getattr(self, attr_name)
            if hasattr(method, "_is_auto_constraint"):  # pylint: disable=protected-access
                constraints = method()
                if isinstance(constraints, list):
                    self._constraints.extend(constraints)
                else:
                    self._constraints.append(constraints)

    def objective_contribution(self):
        return 0.0

    def _uses_legacy_objective(self) -> bool:
        return self.__class__.objective_contribution is not Element.objective_contribution

    def objectives(self) -> List[Objective]:
        declared: List[Objective] = []
        for metadata, method in iter_objective_methods(self):
            expression = method()
            if expression is None:
                continue
            declared.append(
                Objective(
                    name=metadata.name,
                    sense=metadata.sense,
                    expression=expression,
                    weight=metadata.weight,
                    priority=metadata.priority,
                    target=metadata.target,
                    abs_tolerance=metadata.abs_tolerance,
                    rel_tolerance=metadata.rel_tolerance,
                    group=metadata.group,
                    element_name=self.name,
                    method_name=method.__name__,
                )
            )

        if declared and self._uses_legacy_objective():
            raise ValueError(
                f"Element '{self.name}' mixes @objective-decorated methods with "
                "objective_contribution(). Use one objective declaration style per element."
            )

        if declared:
            return declared

        if self._uses_legacy_objective():
            expression = self.objective_contribution()
            if expression is None:
                return []
            sense = normalize_objective_sense(
                getattr(getattr(self, "_model", None), "objective_sense", "minimize")
            )
            return [
                Objective(
                    name="primary",
                    sense=sense,
                    expression=expression,
                    weight=1.0,
                    priority=0,
                    element_name=self.name,
                    method_name="objective_contribution",
                )
            ]

        return []


class ConstraintDecorators:
    @staticmethod
    def auto(func):
        func._is_auto_constraint = True  # pylint: disable=protected-access
        return func


Constraint = ConstraintDecorators
