Examples Overview
=================

Polyhedron includes curated example flows under the `examples/` directory.

If you are new to the modeling layer, the most intuitive progression is usually:

- start with one core domain example close to your problem
- move to indexed modeling once the problem is naturally table-shaped
- then add uncertainty or multi-objective structure only where the business really needs it

Core examples
-------------

- `examples/graph_flow/graph_flow_example.py`
- `examples/heuristics_flow/warm_start_heuristics_example.py`
- `examples/indexed_modeling/indexed_production_example.py`
- `examples/logistics_flow/logistics_data_pipeline_example.py`
- `examples/multi_objective_flow/priority_objectives_example.py`
- `examples/performance_flow/performance_timing_example.py`
- `examples/risk_flow/risk_aware_planning_example.py`
- `examples/selection_flow/project_selection_example.py`
- `examples/task_scheduling/task_scheduling_miqp_example.py`
- `examples/transformation_flow/transformation_primitives_example.py`
- `examples/uc_flow/unit_commitment_example.py`

Bridge example
--------------

- `examples/pyomo_vs_polyhedron/pyomo_comparison_example.py`

Tip
---

Start from the smallest example close to your domain, verify the expected values,
and then add one structural feature at a time: indexing, transformations,
uncertainty, or priority-based objectives. This makes model reviews and regression
tests much easier.
