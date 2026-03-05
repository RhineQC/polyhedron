from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Mapping, Type


def validate_element_kwargs(element_cls: Type[object], kwargs: Mapping[str, object]) -> Dict[str, object]:
    contract = getattr(element_cls, "__data_contract__", None)
    if contract is None:
        return dict(kwargs)

    # Pydantic v2 BaseModel compatibility.
    if hasattr(contract, "model_validate"):
        try:
            instance = contract.model_validate(dict(kwargs))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Data contract validation failed for {element_cls.__name__}: {exc}") from exc
        if hasattr(instance, "model_dump"):
            return dict(instance.model_dump())
        return dict(kwargs)

    # Dataclass compatibility for lightweight schemas.
    if is_dataclass(contract):
        try:
            instance = contract(**dict(kwargs))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Data contract validation failed for {element_cls.__name__}: {exc}") from exc
        return dict(asdict(instance))

    raise TypeError(
        "Unsupported data contract type. Use a pydantic BaseModel (v2) or a dataclass schema."
    )


def with_data_contract(schema: Type[Any]):
    def decorator(element_cls: Type[Any]) -> Type[Any]:
        setattr(element_cls, "__data_contract__", schema)
        return element_cls

    return decorator
