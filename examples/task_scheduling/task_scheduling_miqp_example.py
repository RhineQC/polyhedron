"""Task scheduling MIQP with temporal expansion over a 6-period horizon."""

from __future__ import annotations

from polyhedron import Model
from polyhedron.backends.base import BackendError
from polyhedron.core.expression import QuadraticTerm
from polyhedron.modeling.element import Constraint, Element


class TaskInstance(Element):
    duration = Model.ContinuousVar(min=1.0, max=100.0)
    priority = Model.IntegerVar(min=1, max=5)
    status = Model.BinaryVar()

    def objective_contribution(self):
        return self.duration - 0.5 * self.status - 0.1 * self.priority

    @Constraint.auto
    def priority_time_limit(self):
        return [QuadraticTerm(self.priority, self.status) <= 10 - self.duration]


class UrgentTask(TaskInstance):
    max_duration: float

    def __init__(self, name: str, max_duration: float, **kwargs):
        self.max_duration = max_duration
        super().__init__(name=name, **kwargs)

    @Constraint.auto
    def urgent_cap(self):
        return [self.duration <= self.max_duration]


def main() -> None:
    model = Model("scheduling-demo", solver="scip")

    # Define three tasks and expand them over time with Schedule.
    tsk1 = TaskInstance(name="Task1", duration=5, priority=3, status=1)
    tsk2 = UrgentTask(name="Task2", duration=8, priority=2, status=0, max_duration=7)
    tsk3 = TaskInstance(name="Task3", duration=6, priority=4, status=1)
    horizon = model.TimeHorizon(periods=6, step="1h")
    schedule = model.Schedule([tsk1, tsk2, tsk3], horizon)

    @model.constraint(name="time_limit", foreach=range(6))
    def time_limit(t):
        return (
            schedule[0][t].duration
            + schedule[1][t].duration
            + schedule[2][t].duration
            <= 15
        )

    @model.constraint(name="min_active", foreach=range(6))
    def min_active(t):
        return (
            schedule[0][t].status
            + schedule[1][t].status
            + schedule[2][t].status
            >= 1
        )

    @model.constraint(name="status_duration_link", foreach=range(6))
    def status_duration_link(t):
        return schedule[2][t].duration >= 2 * schedule[2][t].status

    @model.constraint(name="smoothness", foreach=range(1, 6))
    def smoothness(t):
        return schedule[0][t].duration - schedule[0][t - 1].duration <= 3

    try:
        # Solve and print per-period durations and binary activity status.
        solved = model.solve(time_limit=5, return_solved_model=True)
        print("MIQP:", solved.status, solved.objective_value)
        for t in range(6):
            t1 = solved.get_value(schedule[0][t].duration)
            t2 = solved.get_value(schedule[1][t].duration)
            t3 = solved.get_value(schedule[2][t].duration)
            s1 = solved.get_value(schedule[0][t].status)
            s2 = solved.get_value(schedule[1][t].status)
            s3 = solved.get_value(schedule[2][t].status)
            print(f"t={t}: d=[{t1:.1f}, {t2:.1f}, {t3:.1f}] status=[{int(s1)}, {int(s2)}, {int(s3)}]")
    except BackendError as exc:
        print(f"MIQP solve failed: {exc}")


if __name__ == "__main__":
    main()
