from __future__ import annotations

from typing import Any

try:
	from polyhedron.data.pandas import from_dataframe
except ImportError:  # pragma: no cover
	def from_dataframe(*args: Any, **kwargs: Any):
		raise ImportError("pandas is required for polyhedron.data.from_dataframe")

from polyhedron.data.sql import from_sql

__all__ = ["from_dataframe", "from_sql"]
