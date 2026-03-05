import pytest

pytestmark = pytest.mark.data

from polyhedron.modeling.element import Element
from polyhedron.core.model import Model


def _require_data_deps():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    pandas = pytest.importorskip("pandas")
    polars = pytest.importorskip("polars")
    return sqlalchemy, pandas, polars


class Dummy(Element):
    x = Model.ContinuousVar(min=0)
    name: str

    def objective_contribution(self):
        return 0


def test_from_dataframe_mapping():
    _sqlalchemy, pd, _pl = _require_data_deps()
    from polyhedron.data.pandas import from_dataframe

    df = pd.DataFrame([{"col": 1, "name": "a"}])
    items = list(from_dataframe(Dummy, df, mapping={"col": "x"}))
    assert len(items) == 1


def test_from_polars_mapping():
    _sqlalchemy, _pd, pl = _require_data_deps()
    from polyhedron.data.polars import from_polars

    df = pl.DataFrame([{"col": 2, "name": "b"}])
    items = list(from_polars(Dummy, df, mapping={"col": "x"}))
    assert len(items) == 1


def test_from_sql_mapping():
    sqlalchemy, _pd, _pl = _require_data_deps()
    from polyhedron.data.sql import from_sql

    create_engine = sqlalchemy.create_engine
    text = sqlalchemy.text
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE t (name TEXT, col REAL)"))
        conn.execute(text("INSERT INTO t (name, col) VALUES ('c', 3)"))
        items = list(from_sql(Dummy, "SELECT name, col FROM t", conn, mapping={"col": "x"}))
    assert len(items) == 1
