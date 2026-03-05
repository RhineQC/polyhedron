Polyhedron Documentation
========================

.. image:: _static/polyhedron-logo.png
   :alt: Polyhedron logo
   :width: 96px
   :align: right

Polyhedron is a Python optimization modeling framework for teams that need more than
just "build model and solve." It combines a domain-driven modeling DSL with practical
quality and governance tooling so models can be maintained, reviewed, and operated
reliably over time.

Unlike many libraries that focus primarily on algebraic model expression, Polyhedron
puts emphasis on how optimization software is actually used in production:
clear domain abstractions, repeatable diagnostics, scenario workflows, and regression
checks that detect unintended behavior changes before release.

What You Can Do With Polyhedron
-------------------------------

- Model with domain objects (`Element`) instead of flat index-heavy declarations.
- Keep quality high with static linting and explainability reports.
- Diagnose infeasibility in structured reports instead of opaque solver output only.
- Validate units and input contracts early to reduce costly model/debug iterations.
- Run scenario batches and compare baseline vs. current behavior via drift checks.

Who This Is For
---------------

Polyhedron is especially useful for teams building optimization services in energy,
logistics, operations, or planning contexts where model behavior must be transparent,
reviewable, and stable across versions.

If you need only a minimal algebraic layer, other mature libraries may be enough.
If you need modeling plus operational safeguards and lifecycle tooling, Polyhedron is
positioned for that gap.

Minimal Working Example
-----------------------

.. code-block:: python

   from polyhedron import Element, Model


   class Plant(Element):
       production = Model.ContinuousVar(min=0, max=80, unit="MW")

       def objective_contribution(self):
           return 18 * self.production


   model = Model("landing-demo")
   p = Plant("p1")
   model.add_element(p)

   @model.constraint(name="demand")
   def demand():
       return p.production >= 40

   solved = model.solve(return_solved_model=True)
   print(solved.status, solved.get_value(p.production))

Where To Start
--------------

- Installation and setup: :doc:`installation`
- First solve in a few lines: :doc:`quickstart`
- Guided build-up tutorials: :doc:`tutorials/index`
- Task-oriented modeling guides: :doc:`how-to/index`
- Practical usage and operations: :doc:`usage/index`
- Full API and module reference: :doc:`reference/index`

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   quickstart

.. toctree::
   :maxdepth: 2
   :caption: Tutorials

   tutorials/index

.. toctree::
   :maxdepth: 2
   :caption: Usage

   usage/index

.. toctree::
   :maxdepth: 2
   :caption: How-To Guides

   how-to/index

.. toctree::
   :maxdepth: 2
   :caption: Explanations

   explanation/index

.. toctree::
   :maxdepth: 2
   :caption: Reference

   reference/index
