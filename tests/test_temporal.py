import pytest

from polyhedron.temporal.time_horizon import TimeHorizon
from polyhedron.temporal.schedule import Schedule
from polyhedron.modeling.element import Element
from polyhedron.core.model import Model


class Dummy(Element):
    x = Model.ContinuousVar(min=0)

    def objective_contribution(self):
        return 0


def test_time_horizon_validation():
    with pytest.raises(ValueError):
        TimeHorizon(periods=0)


def test_schedule_empty_warns():
    horizon = TimeHorizon(periods=1)
    schedule = Schedule([], horizon)
    assert len(schedule) == 0
