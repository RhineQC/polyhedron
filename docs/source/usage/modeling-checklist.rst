Modeling Checklist
==================

Before solving large models, verify these points.

Structure
---------

- Every `Element` has clear responsibility and bounded variables.
- Prefer `IndexSet`, `Param`, and `VarArray` when the model is naturally keyed by product, site, time, or scenario.
- If domain experts think in tables, make those tables explicit in the model instead of rebuilding the same indexing logic in Python loops.
- Objective contribution is local to each element where possible.
- Constraint names include semantic prefixes (`capacity:`, `balance:`, `ramp:`).
- Use constraint metadata (`group`, `tags`, `index_key`) when the model will be diagnosed or reported later.

Numerics
--------

- Big-M constants are justified and documented.
- Use the provided indicator/disjunction helpers so Big-M logic stays explicit and reviewable.
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
- Prefer `lexicographic` or `epsilon` objective strategies when weighted flattening would hide business intent.
- Use `worst_case`, `cvar`, `chance_constraint`, or `nonanticipativity` only when they correspond to a real operational rule or risk policy that stakeholders can explain.
- Store baseline results with `ModelSnapshot`.
- Enforce regression thresholds for objective and KPI drift.
