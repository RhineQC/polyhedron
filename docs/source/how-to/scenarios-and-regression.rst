Run Scenarios and Regression Checks
===================================

Scenario Batch Runs
-------------------

.. code-block:: python

   from polyhedron import ScenarioCase, ScenarioRunner

   runner = ScenarioRunner(model_factory=build_model)
   report = runner.run(
       [
           ScenarioCase("base"),
           ScenarioCase("best", mutate=lambda m: m.set_factor(0.9)),
           ScenarioCase("worst", mutate=lambda m: m.set_factor(1.2)),
       ]
   )

   print(report.best_feasible())

Regression Drift Checks
-----------------------

.. code-block:: python

   from polyhedron.backends.types import SolveStatus
   from polyhedron.regression import DriftThresholds, ModelSnapshot, compare_snapshots

   baseline = ModelSnapshot(status=SolveStatus.OPTIMAL, objective_value=100.0, kpis={"cost": 100.0})
   current = ModelSnapshot(status=SolveStatus.OPTIMAL, objective_value=104.0, kpis={"cost": 104.0})

   drift = compare_snapshots(
       baseline,
       current,
       thresholds=DriftThresholds(objective_abs=3.0, objective_rel=0.01, kpi_abs=3.0, kpi_rel=0.01),
   )

   print("Passed:", drift.passed)
   print("Issues:", [issue.message for issue in drift.issues])
