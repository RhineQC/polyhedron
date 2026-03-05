from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Tuple


@dataclass(frozen=True)
class UnitDimension:
    powers: Tuple[Tuple[str, int], ...] = ()

    @staticmethod
    def from_mapping(mapping: Mapping[str, int]) -> "UnitDimension":
        normalized = tuple(sorted((key, value) for key, value in mapping.items() if value != 0))
        return UnitDimension(powers=normalized)

    def as_mapping(self) -> Dict[str, int]:
        return {key: value for key, value in self.powers}

    def __mul__(self, other: "UnitDimension") -> "UnitDimension":
        merged = self.as_mapping()
        for key, value in other.powers:
            merged[key] = merged.get(key, 0) + value
            if merged[key] == 0:
                del merged[key]
        return UnitDimension.from_mapping(merged)

    def __truediv__(self, other: "UnitDimension") -> "UnitDimension":
        merged = self.as_mapping()
        for key, value in other.powers:
            merged[key] = merged.get(key, 0) - value
            if merged[key] == 0:
                del merged[key]
        return UnitDimension.from_mapping(merged)

    def __pow__(self, power: int) -> "UnitDimension":
        if power == 0:
            return DIMENSIONLESS
        return UnitDimension.from_mapping({key: value * power for key, value in self.powers})

    def __str__(self) -> str:
        if not self.powers:
            return "1"
        parts = []
        for key, value in self.powers:
            parts.append(f"{key}^{value}" if value != 1 else key)
        return "*".join(parts)


DIMENSIONLESS = UnitDimension()


class UnitRegistry:
    def __init__(self) -> None:
        self._units: Dict[str, UnitDimension] = {}

    def register(self, symbol: str, dimension: UnitDimension) -> None:
        self._units[symbol] = dimension

    def resolve_symbol(self, symbol: str) -> UnitDimension:
        if symbol not in self._units:
            raise ValueError(f"Unknown unit symbol '{symbol}'.")
        return self._units[symbol]

    def parse(self, unit_expression: str) -> UnitDimension:
        expr = unit_expression.strip()
        if not expr or expr == "1":
            return DIMENSIONLESS

        dim = DIMENSIONLESS
        current = ""
        operator = "*"

        def _apply(token: str, op: str, left: UnitDimension) -> UnitDimension:
            token = token.strip()
            if not token:
                return left
            if "^" in token:
                base, exp_text = token.split("^", 1)
                exponent = int(exp_text.strip())
            else:
                base = token
                exponent = 1
            base_dim = self.resolve_symbol(base.strip()) ** exponent
            return left * base_dim if op == "*" else left / base_dim

        for ch in expr:
            if ch in "*/":
                dim = _apply(current, operator, dim)
                current = ""
                operator = ch
            else:
                current += ch
        dim = _apply(current, operator, dim)
        return dim

    @classmethod
    def default(cls) -> "UnitRegistry":
        registry = cls()
        registry.register("MW", UnitDimension.from_mapping({"power": 1}))
        registry.register("kW", UnitDimension.from_mapping({"power": 1}))
        registry.register("MWh", UnitDimension.from_mapping({"energy": 1}))
        registry.register("kWh", UnitDimension.from_mapping({"energy": 1}))
        registry.register("h", UnitDimension.from_mapping({"time": 1}))
        registry.register("EUR", UnitDimension.from_mapping({"currency": 1}))
        registry.register("USD", UnitDimension.from_mapping({"currency": 1}))
        registry.register("kg", UnitDimension.from_mapping({"mass": 1}))
        registry.register("km", UnitDimension.from_mapping({"length": 1}))
        return registry


def dimensions_equal(left: UnitDimension, right: UnitDimension) -> bool:
    return left.powers == right.powers


def first_non_dimensionless(dimensions: Iterable[UnitDimension]) -> UnitDimension:
    for dim in dimensions:
        if dim != DIMENSIONLESS:
            return dim
    return DIMENSIONLESS
