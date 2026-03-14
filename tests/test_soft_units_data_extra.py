import pytest

from polyhedron.core.constraint import Constraint
from polyhedron.core.model import Model
from polyhedron.modeling.soft_constraints import SoftConstraint, soften_constraint
from polyhedron.units.dimensions import DIMENSIONLESS, UnitDimension, UnitRegistry, dimensions_equal, first_non_dimensionless


class DataElement:
    def __init__(self, a=None, b=None):
        self.a = a
        self.b = b


class T:
    x = Model.ContinuousVar(min=0, max=10)


def test_soft_constraint_all_senses_and_errors() -> None:
    model = Model("soft")
    le = Constraint(lhs=1, sense="<=", rhs=2, name="le")
    ge = Constraint(lhs=3, sense=">=", rhs=1, name="ge")
    eq = Constraint(lhs=2, sense="==", rhs=2, name="eq")

    s1 = SoftConstraint(model, le, weight=10, name="s1", max_violation=5)
    s2 = SoftConstraint(model, ge, weight=10, name="s2", max_violation=5)
    s3 = SoftConstraint(model, eq, weight=10, name="s3", max_violation=5)

    r1 = s1.add_to_model()
    r2 = s2.add_to_model()
    r3 = s3.add_to_model()

    assert r1.name == "s1"
    assert r2.name == "s2"
    assert r3.name == "s3"
    assert len(model.constraints) == 3

    with pytest.raises(ValueError, match="max_violation must be positive"):
        SoftConstraint(model, le, weight=1, max_violation=0).add_to_model()

    bad = Constraint(lhs=1, sense="!=", rhs=1, name="bad")
    with pytest.raises(ValueError, match="Unsupported constraint sense"):
        SoftConstraint(model, bad, weight=1).add_to_model()

    soft = soften_constraint(model, le, weight=2, name="wrapped", max_violation=4)
    assert soft.relaxed_constraint is not None


def test_units_dimension_operations_and_registry_parse() -> None:
    d_power = UnitDimension.from_mapping({"power": 1, "x": 0})
    d_time = UnitDimension.from_mapping({"time": 1})

    mul = d_power * d_time
    div = mul / d_time
    pow0 = d_power ** 0
    pow2 = d_power ** 2

    assert str(d_power) == "power"
    assert str(pow2) == "power^2"
    assert pow0 == DIMENSIONLESS
    assert div == d_power

    registry = UnitRegistry.default()
    dim = registry.parse("MW*h/MWh")
    assert isinstance(dim, UnitDimension)

    with pytest.raises(ValueError, match="Unknown unit symbol"):
        registry.resolve_symbol("NOPE")

    assert dimensions_equal(d_power, UnitDimension.from_mapping({"power": 1}))
    assert first_non_dimensionless([DIMENSIONLESS, d_time]) == d_time


@pytest.mark.data
def test_data_pandas_polars_sql_success_and_errors() -> None:
    _sqlalchemy = pytest.importorskip("sqlalchemy")
    pd = pytest.importorskip("pandas")
    pl = pytest.importorskip("polars")
    from polyhedron.data.pandas import from_dataframe
    from polyhedron.data.polars import from_polars
    from polyhedron.data.sql import from_sql

    class Good:
        def __init__(self, a=None, b=None):
            self.a = a
            self.b = b

    class Bad:
        def __init__(self, a=None):
            if a is None:
                raise ValueError("a required")
            self.a = a

    pdf = pd.DataFrame([{"a": 1, "b": 2}])
    out = list(from_dataframe(Good, pdf, mapping={"a": "a", "b": "b"}))
    assert out[0].a == 1

    class BadDF:
        def __len__(self):
            return 1

        def to_dict(self, orient=None):
            raise RuntimeError("bad")

    with pytest.raises(Exception, match="E_DATA_FRAME"):
        list(from_dataframe(Good, BadDF()))

    with pytest.raises(Exception, match="E_DATA_ELEMENT"):
        list(from_dataframe(Bad, pd.DataFrame([{"b": 2}])))

    pldf = pl.DataFrame([{"a": 1, "b": 2}])
    out2 = list(from_polars(Good, pldf))
    assert out2[0].b == 2

    class BadPL:
        height = 1

        def to_dicts(self):
            raise RuntimeError("bad")

    with pytest.raises(Exception, match="E_DATA_POLARS"):
        list(from_polars(Good, BadPL()))

    with pytest.raises(Exception, match="E_DATA_ELEMENT"):
        list(from_polars(Bad, pl.DataFrame([{"b": 1}])))

    class Conn:
        def execute(self, _query):
            class Result:
                def mappings(self_inner):
                    return [{"a": 7, "b": 8}]

            return Result()

    out3 = list(from_sql(Good, "select 1", Conn()))
    assert out3[0].a == 7

    class BadConn:
        def execute(self, _query):
            raise RuntimeError("sql")

    with pytest.raises(Exception, match="E_DATA_SQL"):
        list(from_sql(Good, "select", BadConn()))

    class ConnBadRow:
        def execute(self, _query):
            class Result:
                def mappings(self_inner):
                    return [{"b": 9}]

            return Result()

    with pytest.raises(Exception, match="E_DATA_ELEMENT"):
        list(from_sql(Bad, "select", ConnBadRow()))
