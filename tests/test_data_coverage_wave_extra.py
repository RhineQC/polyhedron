from __future__ import annotations

from dataclasses import dataclass

import pytest


@dataclass
class RowElement:
    name: str
    value: int


def test_from_dataframe_conversion_error(monkeypatch):
    pd = pytest.importorskip("pandas")
    from polyhedron.core.errors import DataError
    from polyhedron.data.pandas import from_dataframe

    class BrokenDF(pd.DataFrame):
        def to_dict(self, *args, **kwargs):
            raise RuntimeError("boom")

    df = BrokenDF({"name": ["a"], "value": [1]})
    with pytest.raises(DataError, match="Failed to convert DataFrame to records"):
        list(from_dataframe(RowElement, df))


def test_from_polars_conversion_error(monkeypatch):
    pl = pytest.importorskip("polars")
    from polyhedron.core.errors import DataError
    from polyhedron.data.polars import from_polars

    class BrokenPLDF(pl.DataFrame):
        def to_dicts(self):
            raise RuntimeError("boom")

    df = BrokenPLDF({"name": ["a"], "value": [1]})
    with pytest.raises(DataError, match="Failed to convert Polars DataFrame to records"):
        list(from_polars(RowElement, df))


def test_from_sql_success_and_mapping(monkeypatch):
    from polyhedron.data import sql as sql_mod
    from polyhedron.data.sql import from_sql

    monkeypatch.setattr(sql_mod, "_sa_text", lambda q: q)

    class FakeResult:
        def mappings(self):
            return iter([{"n": "a", "v": 1}, {"n": "b", "v": 2}])

    class FakeConnection:
        def execute(self, statement):
            assert statement == "select n, v from t"
            return FakeResult()

    rows = list(
        from_sql(
            RowElement,
            "select n, v from t",
            FakeConnection(),
            mapping={"n": "name", "v": "value"},
        )
    )
    assert [r.name for r in rows] == ["a", "b"]
    assert [r.value for r in rows] == [1, 2]


def test_from_sql_execute_error(monkeypatch):
    from polyhedron.core.errors import DataError
    from polyhedron.data import sql as sql_mod
    from polyhedron.data.sql import from_sql

    monkeypatch.setattr(sql_mod, "_sa_text", lambda q: q)

    class BadConnection:
        def execute(self, statement):
            raise RuntimeError("db down")

    with pytest.raises(DataError, match="Failed to execute SQL query"):
        list(from_sql(RowElement, "select 1", BadConnection()))


def test_from_sql_element_build_error(monkeypatch):
    from polyhedron.core.errors import DataError
    from polyhedron.data import sql as sql_mod
    from polyhedron.data.sql import from_sql

    monkeypatch.setattr(sql_mod, "_sa_text", lambda q: q)

    class FakeResult:
        def mappings(self):
            return iter([{"name": "a", "value": 1}])

    class FakeConnection:
        def execute(self, statement):
            return FakeResult()

    class NeedsExtra:
        def __init__(self, name: str, value: int, extra: str):
            self.name = name
            self.value = value
            self.extra = extra

    with pytest.raises(DataError, match="Failed to construct element from SQL row"):
        list(from_sql(NeedsExtra, "select name, value from t", FakeConnection()))
