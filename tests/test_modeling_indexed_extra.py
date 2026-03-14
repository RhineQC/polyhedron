from polyhedron import Element, Model
from polyhedron.modeling import IndexSet, IndexedElement, sum_over


class IndexedFlowElement(Element):
    flow = Model.ContinuousVar(min=0, max=10)

    def objective_contribution(self):
        return self.flow


def test_index_set_param_var_array_and_sum_over() -> None:
    model = Model("indexed")
    products = model.index_set("products", ["a", "b"])
    periods = IndexSet("periods", [0, 1])
    grid = products.product(periods, name="product_period")
    demand = model.param("demand", {("a", 0): 3, ("a", 1): 4, ("b", 0): 2, ("b", 1): 5}, index_set=grid)
    flow = model.var_array("ship", grid, lower_bound=0.0, upper_bound=10.0)

    assert flow[("a", 0)].name == "ship[a,0]"
    assert demand[("b", 1)] == 5

    constraints = model.forall(
        grid,
        lambda product, period: flow[(product, period)] >= demand[(product, period)],
        name="meet_demand",
        group="demand",
        tags=("indexed",),
    )

    assert len(constraints) == 4
    assert constraints[0].group == "demand"
    assert constraints[0].tags == ("indexed",)

    objective = sum_over(grid, lambda key: flow[key])
    assert objective.terms


def test_indexed_element_builds_and_adds_elements() -> None:
    model = Model("indexed-elements")
    nodes = model.index_set("nodes", ["n1", "n2", "n3"])
    fleet = IndexedElement.build(name="fleet", index_set=nodes, factory=lambda key: IndexedFlowElement(f"unit_{key}"))
    fleet.add_to_model(model)

    assert len(model.elements) == 3
    assert fleet["n2"].name == "unit_n2"