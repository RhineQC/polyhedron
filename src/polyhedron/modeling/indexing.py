from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, Hashable, Iterable, Iterator, Mapping, Optional, Sequence, TypeVar

from polyhedron.core.variable import VarType, Variable
from polyhedron.modeling.element import Element


IndexKey = TypeVar("IndexKey", bound=Hashable)
ValueT = TypeVar("ValueT")


def _label_key(key: object) -> str:
    if isinstance(key, tuple):
        return ",".join(_label_key(part) for part in key)
    return str(key)


@dataclass(frozen=True)
class IndexSet(Generic[IndexKey]):
    name: str
    items: tuple[IndexKey, ...]

    def __init__(self, name: str, items: Iterable[IndexKey]):
        object.__setattr__(self, "name", str(name))
        object.__setattr__(self, "items", tuple(items))

    def __iter__(self) -> Iterator[IndexKey]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, item: object) -> bool:
        return item in self.items

    def where(self, predicate: Callable[[IndexKey], bool], *, name: str | None = None) -> "IndexSet[IndexKey]":
        return IndexSet(name or self.name, (item for item in self.items if predicate(item)))

    def map(self, mapper: Callable[[IndexKey], ValueT]) -> tuple[ValueT, ...]:
        return tuple(mapper(item) for item in self.items)

    def product(self, *others: "IndexSet[object]", name: str | None = None) -> "IndexSet[tuple[object, ...]]":
        tuples: list[tuple[object, ...]] = [(item,) for item in self.items]
        for other in others:
            tuples = [left + (right,) for left in tuples for right in other.items]
        product_name = name or " x ".join([self.name, *(other.name for other in others)])
        return IndexSet(product_name, tuples)


@dataclass(frozen=True)
class Param(Generic[IndexKey, ValueT]):
    name: str
    values: Mapping[IndexKey, ValueT]
    index_set: Optional[IndexSet[IndexKey]] = None
    default: Optional[ValueT] = None

    def __getitem__(self, key: IndexKey) -> ValueT:
        if key in self.values:
            return self.values[key]
        if self.default is not None:
            return self.default
        raise KeyError(key)

    def get(self, key: IndexKey, default: ValueT | None = None) -> ValueT | None:
        if key in self.values:
            return self.values[key]
        if default is not None:
            return default
        return self.default

    def items_view(self) -> tuple[tuple[IndexKey, ValueT], ...]:
        if self.index_set is None:
            return tuple(self.values.items())
        return tuple((key, self[key]) for key in self.index_set)


class _VariableCarrier(Element):
    def __init__(self, name: str, variables: Mapping[str, Variable]):
        super().__init__(name)
        self._variables = dict(variables)

    def objective_contribution(self):
        return 0.0


@dataclass(frozen=True)
class VarArray(Generic[IndexKey]):
    name: str
    index_set: IndexSet[IndexKey]
    variables: Mapping[IndexKey, Variable]

    def __getitem__(self, key: IndexKey) -> Variable:
        return self.variables[key]

    def items(self) -> tuple[tuple[IndexKey, Variable], ...]:
        return tuple((key, self.variables[key]) for key in self.index_set)

    def keys(self) -> tuple[IndexKey, ...]:
        return self.index_set.items

    def values(self) -> tuple[Variable, ...]:
        return tuple(self.variables[key] for key in self.index_set)

    def where(self, predicate: Callable[[IndexKey], bool]) -> "VarArray[IndexKey]":
        filtered = self.index_set.where(predicate, name=self.index_set.name)
        return VarArray(self.name, filtered, {key: self.variables[key] for key in filtered})

    def sum(self, terms: Callable[[IndexKey, Variable], object] | None = None):
        if terms is None:
            return sum((self.variables[key] for key in self.index_set), 0.0)
        return sum((terms(key, self.variables[key]) for key in self.index_set), 0.0)

    @classmethod
    def build(
        cls,
        *,
        model,
        name: str,
        index_set: IndexSet[IndexKey],
        var_type: VarType,
        lower_bound: float,
        upper_bound: float,
        unit: str | None = None,
    ) -> "VarArray[IndexKey]":
        variables = {
            key: Variable(
                name=f"{name}[{_label_key(key)}]",
                var_type=var_type,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                unit=unit,
            )
            for key in index_set
        }
        carrier = _VariableCarrier(f"{name}__carrier", {str(key): var for key, var in variables.items()})
        model.add_element(carrier)
        return cls(name=name, index_set=index_set, variables=variables)


@dataclass(frozen=True)
class IndexedElement(Generic[IndexKey]):
    name: str
    index_set: IndexSet[IndexKey]
    elements: Mapping[IndexKey, Element]

    def __getitem__(self, key: IndexKey) -> Element:
        return self.elements[key]

    def values(self) -> tuple[Element, ...]:
        return tuple(self.elements[key] for key in self.index_set)

    def add_to_model(self, model) -> "IndexedElement[IndexKey]":
        model.add_elements(self.values())
        return self

    @classmethod
    def build(
        cls,
        *,
        name: str,
        index_set: IndexSet[IndexKey],
        factory: Callable[[IndexKey], Element],
    ) -> "IndexedElement[IndexKey]":
        return cls(name=name, index_set=index_set, elements={key: factory(key) for key in index_set})


def sum_over(
    index_set: Iterable[IndexKey],
    expr: Callable[[IndexKey], object],
    *,
    where: Callable[[IndexKey], bool] | None = None,
):
    return sum((expr(item) for item in index_set if where is None or where(item)), 0.0)


def where(index_set: Iterable[IndexKey], predicate: Callable[[IndexKey], bool]) -> tuple[IndexKey, ...]:
    return tuple(item for item in index_set if predicate(item))


__all__ = [
    "IndexSet",
    "Param",
    "VarArray",
    "IndexedElement",
    "sum_over",
    "where",
]