from __future__ import annotations

from typing import Dict, Iterable, Optional, Type

from sqlalchemy import text

from polyhedron.core.errors import DataError


def from_sql(
    element_cls: Type,
    query: str,
    connection,
    mapping: Optional[Dict[str, str]] = None,
) -> Iterable:
    try:
        result = connection.execute(text(query))
    except Exception as exc:  # noqa: BLE001
        raise DataError(
            code="E_DATA_SQL",
            message="Failed to execute SQL query.",
            context={"query": query},
            remediation="Validate SQL syntax and connection.",
            origin="polyhedron.data.sql",
        ) from exc

    for row in result.mappings():
        record = dict(row)
        if mapping:
            record = {mapping.get(k, k): v for k, v in record.items()}
        try:
            yield element_cls(**record)
        except Exception as exc:  # noqa: BLE001
            raise DataError(
                code="E_DATA_ELEMENT",
                message="Failed to construct element from SQL row.",
                context={"row": record, "element": getattr(element_cls, "__name__", None)},
                remediation="Check mapping and element __init__ signature.",
                origin="polyhedron.data.sql",
            ) from exc
