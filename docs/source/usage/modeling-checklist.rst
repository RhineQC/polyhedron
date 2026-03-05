Modeling Checklist
==================

Before solving large models, verify these points.

Structure
---------

- Every `Element` has clear responsibility and bounded variables.
- Objective contribution is local to each element where possible.
- Constraint names include semantic prefixes (`capacity:`, `balance:`, `ramp:`).

Numerics
--------

- Big-M constants are justified and documented.
- Coefficients are not spread across extreme scales.
- Integer domains are used only where truly needed.

Diagnostics
-----------

- Run `lint_model(model)` and resolve warnings/errors.
- Run `explain_model(model)` and inspect bottlenecks.
- If infeasible, run `debug_infeasibility(model, candidate)` with a candidate assignment.

Governance
----------

- Attach input contracts via `with_data_contract` for critical elements.
- Store baseline results with `ModelSnapshot`.
- Enforce regression thresholds for objective and KPI drift.
