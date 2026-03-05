from __future__ import annotations

from typing import Dict, Iterable, Optional, Type

import polars as pl

from polyhedron.core.errors import DataError


def from_polars(element_cls: Type, df: pl.DataFrame, mapping: Optional[Dict[str, str]] = None) -> Iterable:
    try:
        records = df.to_dicts()
    except Exception as exc:  # noqa: BLE001
        raise DataError(
            code="E_DATA_POLARS",
            message="Failed to convert Polars DataFrame to records.",
            context={"rows": df.height},
            remediation="Ensure DataFrame is valid and serializable.",
            origin="polyhedron.data.polars",
        ) from exc
    for record in records:
        if mapping:
            record = {mapping.get(k, k): v for k, v in record.items()}
        try:
            yield element_cls(**record)
        except Exception as exc:  # noqa: BLE001
            raise DataError(
                code="E_DATA_ELEMENT",
                message="Failed to construct element from Polars record.",
                context={"record": record, "element": getattr(element_cls, "__name__", None)},
                remediation="Check mapping and element __init__ signature.",
                origin="polyhedron.data.polars",
            ) from exc
