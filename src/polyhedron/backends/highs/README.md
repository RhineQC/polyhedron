HiGHS backend implementation for Polyhedron.

This backend is powered by `highspy` and supports the standard Polyhedron solve
API, including time limits, relative MIP gaps, warm starts, solve callbacks,
and heuristic-driven candidate injection through the HiGHS callback interface.

Variable hints are mapped to warm starts because HiGHS does not expose a
separate hint API, and branching priorities are currently ignored for the same
reason.
