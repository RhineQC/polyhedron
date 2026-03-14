Indexed Modeling
================

Use ``IndexSet``, ``Param``, ``VarArray``, and ``Model.forall(...)`` when the model
is naturally expressed over keys such as product, site, period, or scenario.

The central design point of Polyhedron is the domain logic. Indexed modeling extends
domain models once a single plant, route, contract, or task turns into a family of
related objects.

This is the right tool whenever domain experts already think in a rectangular or
keyed structure. In practice that often means tables such as “demand by product and
week”, “capacity by site and shift”, or “inventory by item and warehouse”.

Without an indexed layer, those models usually turn into nested Python loops,
manually synchronized dictionaries, and constraint generators that are hard to read
after a few months. ``IndexSet`` and friends give the key structure a first-class
representation so the code stays aligned with the business view of the problem.

For Polyhedron specifically, the most important question is often not “how do I make
the index math work?” but “which part of the model should stay a domain object and
which part should become a dense indexed decision family?” In many real models,
``IndexedElement`` is the main answer.

Indexed Elements First
----------------------

If each key represents a real business or physical entity, start with
``IndexedElement``.

.. code-block:: python

   class ProductionUnit(Element):
       output = Model.ContinuousVar(min=0, max=80)

       product: str
       variable_cost: float

       def objective_contribution(self):
           return self.variable_cost * self.output


   products = model.index_set("products", ["A", "B", "C"])
   variable_cost = {"A": 9.0, "B": 11.0, "C": 8.5}

   units = model.indexed(
       "units",
       products,
       lambda product: ProductionUnit(
           f"unit_{product}",
           product=product,
           variable_cost=variable_cost[product],
       ),
   )
   units.add_to_model(model)

This is often the cleanest style because it preserves the domain vocabulary. The
code talks about units, products, sites, or contracts rather than turning the whole
model into bare arrays immediately.

Use ``VarArray`` when the object itself is not the focus, but the indexed decision is.
Typical examples are transport flows on a dense network, piecewise weights, scenario
selectors, lambda variables, or other algebraic helper families.

Define Index Sets And Parameters
--------------------------------

Think of an ``IndexSet`` as the model-side definition of a business axis. It says
which keys exist and in which order they should be traversed.

.. code-block:: python

   products = model.index_set("products", ["A", "B"])
   periods = model.index_set("periods", [0, 1, 2])
   grid = products.product(periods, name="product_period")

   demand = model.param(
       "demand",
       {
           ("A", 0): 4,
           ("A", 1): 5,
           ("A", 2): 6,
           ("B", 0): 3,
           ("B", 1): 4,
           ("B", 2): 4,
       },
       index_set=grid,
   )

``products`` and ``periods`` are one-dimensional axes. ``grid`` is their Cartesian
product, so each key in ``grid`` is a pair ``(product, period)``. ``Param`` then
attaches data to exactly those keys. That makes it immediately visible which entries
are expected by the model and prevents silent drift between input data and decision
structure.

Create Indexed Variable Families
--------------------------------

``VarArray`` creates one decision variable per key in the index set.

.. code-block:: python

   production = model.var_array(
       "production",
       grid,
       lower_bound=0.0,
       upper_bound=20.0,
   )

   assert production[("A", 0)].name == "production[A,0]"

You can read ``production[("A", 0)]`` as “the production decision for product A in
period 0”. That small shift matters in practice because it makes model reviews much
easier for planners and analysts who are validating the formulation.

Quantified Builders
-------------------

``Model.forall(...)`` lets you attach indexed constraints without leaving the
core Polyhedron style.

.. code-block:: python

   model.forall(
       grid,
       lambda product, period: production[(product, period)] >= demand[(product, period)],
       name="meet_demand",
       group="balance",
       tags=("indexed",),
   )

``Model.sum_over(...)`` and ``sum_over(...)`` provide the matching indexed sum helper.

.. code-block:: python

   total_output = model.sum_over(grid, lambda key: production[key])

Mathematically, ``forall`` means “create one constraint for every admissible key”
and ``sum_over`` means “sum the expression across the key set”. Intuitively, they
let you say “for every product and period, satisfy demand” and “sum all production”
without dropping down into bookkeeping code.

This becomes particularly valuable once conditions are involved. A filtered index set
or a ``where=...`` predicate lets you express ideas like “only for peak periods” or
“only for products handled by this plant” in a way that remains visible in the code.

Indexed Elements In Hybrid Models
---------------------------------

If the model is most naturally described with domain objects, use
``IndexedElement`` to build keyed element families.

.. code-block:: python

   fleet = model.indexed(
       "fleet",
       products,
       lambda product: ProductionUnit(f"unit_{product}", product=product),
   )
   fleet.add_to_model(model)

This gives you stable domain objects and stable keys at the same time. A common
pattern is to use ``IndexedElement`` for physical or business entities and
``VarArray`` for dense algebraic decision families that live around them.

Choosing between these styles is not an all-or-nothing decision. Polyhedron supports
hybrid models where domain objects, indexed variables, and quantified builders all
participate in the same formulation.

That hybrid style is usually the most natural one for production models:

- domain objects hold local behavior, local data, and local objectives
- indexed variable families represent dense algebraic structures around those objects
- quantified builders connect the two without losing readable keys

If you are unsure where to start, start with ``Element`` and move to ``IndexedElement``
before reaching for large free-floating arrays. That preserves the main strength of
Polyhedron: domain-driven model structure.