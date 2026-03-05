from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from polyhedron.contracts.runtime import validate_element_kwargs
from polyhedron.core.constraint import Constraint
from polyhedron.core.variable import VariableDefinition


class Element(ABC):
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

    @abstractmethod
    def objective_contribution(self):
        raise NotImplementedError


class ConstraintDecorators:
    @staticmethod
    def auto(func):
        func._is_auto_constraint = True  # pylint: disable=protected-access
        return func


Constraint = ConstraintDecorators
