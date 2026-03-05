from polyhedron import Model
from polyhedron.modeling.selection import SelectableElement, SelectionGroup


class Item(SelectableElement):
    cost: float

    def objective_contribution(self):
        return 0.0


def test_selection_group_constraints():
    model = Model("selection-test")
    items = [Item("A", cost=3.0), Item("B", cost=4.0)]

    group = SelectionGroup(model=model, elements=items).add_to_model()
    constraint_exact = group.choose_exactly(1, name="pick_one")
    constraint_budget = group.budget_limit(5.0, weight_attr="cost", name="budget")

    assert constraint_exact in model.constraints
    assert constraint_budget in model.constraints
    assert constraint_exact.name == "pick_one"
    assert constraint_exact.sense == "=="
    assert constraint_budget.name == "budget"
    assert constraint_budget.sense == "<="
    assert len(group.selectors()) == 2


def test_selected_elements_from_values():
    model = Model("selection-values")
    items = [Item("A", cost=1.0), Item("B", cost=2.0)]
    group = SelectionGroup(model=model, elements=items).add_to_model()

    values = {items[0].selected: 1.0, items[1].selected: 0.0}
    selected = group.selected_elements(values)

    assert selected == [items[0]]
