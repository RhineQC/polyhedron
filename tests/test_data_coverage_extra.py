"""Tests for data module: pandas and polars integration."""
from __future__ import annotations

import pytest

from polyhedron.core.errors import DataError


pytestmark = pytest.mark.data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class Item:
    def __init__(self, name: str, value: float):
        self.name = name
        self.value = value


# ---------------------------------------------------------------------------
# pandas
# ---------------------------------------------------------------------------

class TestFromDataframe:
    def test_basic_yield(self):
        pd = pytest.importorskip("pandas")
        from polyhedron.data.pandas import from_dataframe

        df = pd.DataFrame([{"name": "alpha", "value": 1.0}])
        result = list(from_dataframe(Item, df))
        assert len(result) == 1
        assert result[0].name == "alpha"
        assert result[0].value == 1.0

    def test_multiple_rows(self):
        pd = pytest.importorskip("pandas")
        from polyhedron.data.pandas import from_dataframe

        df = pd.DataFrame([{"name": "a", "value": 1.0}, {"name": "b", "value": 2.0}])
        result = list(from_dataframe(Item, df))
        assert len(result) == 2

    def test_with_mapping(self):
        pd = pytest.importorskip("pandas")
        from polyhedron.data.pandas import from_dataframe

        df = pd.DataFrame([{"n": "beta", "v": 3.5}])
        result = list(from_dataframe(Item, df, mapping={"n": "name", "v": "value"}))
        assert result[0].name == "beta"
        assert result[0].value == pytest.approx(3.5)

    def test_raises_data_error_on_bad_record(self):
        pd = pytest.importorskip("pandas")
        from polyhedron.data.pandas import from_dataframe

        df = pd.DataFrame([{"wrong_field": "x"}])
        with pytest.raises(DataError):
            list(from_dataframe(Item, df))

    def test_empty_dataframe_yields_nothing(self):
        pd = pytest.importorskip("pandas")
        from polyhedron.data.pandas import from_dataframe

        df = pd.DataFrame(columns=["name", "value"])
        result = list(from_dataframe(Item, df))
        assert result == []


# ---------------------------------------------------------------------------
# polars
# ---------------------------------------------------------------------------

class TestFromPolars:
    def test_basic_yield(self):
        pl = pytest.importorskip("polars")
        from polyhedron.data.polars import from_polars

        df = pl.DataFrame([{"name": "gamma", "value": 2.0}])
        result = list(from_polars(Item, df))
        assert len(result) == 1
        assert result[0].name == "gamma"

    def test_multiple_rows(self):
        pl = pytest.importorskip("polars")
        from polyhedron.data.polars import from_polars

        df = pl.DataFrame([{"name": "x", "value": 1.0}, {"name": "y", "value": 2.0}])
        result = list(from_polars(Item, df))
        assert len(result) == 2

    def test_with_mapping(self):
        pl = pytest.importorskip("polars")
        from polyhedron.data.polars import from_polars

        df = pl.DataFrame([{"n": "delta", "v": 7.0}])
        result = list(from_polars(Item, df, mapping={"n": "name", "v": "value"}))
        assert result[0].name == "delta"

    def test_raises_data_error_on_bad_record(self):
        pl = pytest.importorskip("polars")
        from polyhedron.data.polars import from_polars

        df = pl.DataFrame([{"wrong_field": "y"}])
        with pytest.raises(DataError):
            list(from_polars(Item, df))

    def test_empty_dataframe_yields_nothing(self):
        pl = pytest.importorskip("polars")
        from polyhedron.data.polars import from_polars

        df = pl.DataFrame(schema={"name": pl.Utf8, "value": pl.Float64})
        result = list(from_polars(Item, df))
        assert result == []
