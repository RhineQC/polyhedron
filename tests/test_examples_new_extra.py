from __future__ import annotations

from pathlib import Path
import runpy


EXAMPLES = [
    "examples/indexed_modeling/indexed_production_example.py",
    "examples/transformation_flow/transformation_primitives_example.py",
    "examples/risk_flow/risk_aware_planning_example.py",
    "examples/multi_objective_flow/priority_objectives_example.py",
]


def test_new_examples_execute_without_unhandled_errors() -> None:
    root = Path(__file__).resolve().parents[1]
    for example in EXAMPLES:
        runpy.run_path(str(root / example), run_name="__main__")