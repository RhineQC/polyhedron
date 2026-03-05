from __future__ import annotations

from typing import Dict, Iterable, Optional, Type

import pandas as pd

from polyhedron.core.errors import DataError


def from_dataframe(element_cls: Type, df: pd.DataFrame, mapping: Optional[Dict[str, str]] = None) -> Iterable:
    try:
        records = df.to_dict(orient="records")
    except Exception as exc:  # noqa: BLE001
        raise DataError(
            code="E_DATA_FRAME",
            message="Failed to convert DataFrame to records.",
            context={"rows": len(df)},
            remediation="Ensure DataFrame is valid and serializable.",
            origin="polyhedron.data.pandas",
        ) from exc
    for record in records:
        if mapping:
            record = {mapping.get(k, k): v for k, v in record.items()}
        try:
            yield element_cls(**record)
        except Exception as exc:  # noqa: BLE001
            raise DataError(
                code="E_DATA_ELEMENT",
                message="Failed to construct element from DataFrame record.",
                context={"record": record, "element": getattr(element_cls, "__name__", None)},
                remediation="Check mapping and element __init__ signature.",
                origin="polyhedron.data.pandas",
            ) from exc
