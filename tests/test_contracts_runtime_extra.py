from dataclasses import dataclass

import pytest

from polyhedron.contracts.runtime import validate_element_kwargs, with_data_contract
from polyhedron.modeling.element import Element


class NoContractElement(Element):
    def objective_contribution(self):
        return 0


def test_validate_kwargs_without_contract_returns_copy() -> None:
    kwargs = {"a": 1}
    out = validate_element_kwargs(NoContractElement, kwargs)
    assert out == {"a": 1}
    assert out is not kwargs


class FakePydanticInstance:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return {"normalized": self._payload["x"] + 1}


class FakePydanticContract:
    @staticmethod
    def model_validate(payload):
        if payload["x"] < 0:
            raise ValueError("x must be >= 0")
        return FakePydanticInstance(payload)


class FakePydanticNoDump:
    @staticmethod
    def model_validate(payload):
        return object()


class PydanticElement(Element):
    __data_contract__ = FakePydanticContract

    def objective_contribution(self):
        return 0


class PydanticNoDumpElement(Element):
    __data_contract__ = FakePydanticNoDump

    def objective_contribution(self):
        return 0


def test_validate_kwargs_with_pydantic_like_contract_uses_model_dump() -> None:
    out = validate_element_kwargs(PydanticElement, {"x": 4})
    assert out == {"normalized": 5}


def test_validate_kwargs_with_pydantic_like_contract_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Data contract validation failed"):
        validate_element_kwargs(PydanticElement, {"x": -1})


def test_validate_kwargs_with_pydantic_like_contract_without_dump_returns_input() -> None:
    out = validate_element_kwargs(PydanticNoDumpElement, {"x": 2})
    assert out == {"x": 2}


@dataclass
class DataSchema:
    amount: int


class DataclassElement(Element):
    __data_contract__ = DataSchema

    def objective_contribution(self):
        return 0


def test_validate_kwargs_with_dataclass_contract() -> None:
    out = validate_element_kwargs(DataclassElement, {"amount": 7})
    assert out == {"amount": 7}


def test_validate_kwargs_with_unsupported_contract_type() -> None:
    class UnsupportedElement(Element):
        __data_contract__ = int

        def objective_contribution(self):
            return 0

    with pytest.raises(TypeError, match="Unsupported data contract type"):
        validate_element_kwargs(UnsupportedElement, {"v": 1})


def test_with_data_contract_decorator_sets_schema() -> None:
    @with_data_contract(DataSchema)
    class DecoratedElement(Element):
        def objective_contribution(self):
            return 0

    assert getattr(DecoratedElement, "__data_contract__") is DataSchema
