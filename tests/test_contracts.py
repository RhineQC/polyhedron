from dataclasses import dataclass

import pytest

from polyhedron import Model
from polyhedron.contracts import with_data_contract
from polyhedron.modeling.element import Element


@dataclass
class PlantSchema:
    capacity: float

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")


@with_data_contract(PlantSchema)
class ContractElement(Element):
    x = Model.ContinuousVar(min=0.0)

    capacity: float

    def objective_contribution(self):
        return self.x


def test_data_contract_accepts_valid_payload() -> None:
    elem = ContractElement("c1", capacity=10.0)
    assert elem.capacity == 10.0


def test_data_contract_rejects_invalid_payload() -> None:
    with pytest.raises(ValueError):
        ContractElement("c2", capacity=-1.0)
