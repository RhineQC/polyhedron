"""
Comprehensive MILP/SCIP tests that verify optimal solutions
for multiple constraint/encoding patterns.
"""
import pytest

from polyhedron import Model
from polyhedron.backends.types import SolveStatus
from polyhedron.core.constraint import Constraint
from polyhedron.modeling.element import Element

pytestmark = pytest.mark.scip


def _solve(model, time_limit=2.0):
    solved = model.solve(time_limit=time_limit, mip_gap=0.0, return_solved_model=True)
    assert solved.status in {SolveStatus.OPTIMAL, SolveStatus.FEASIBLE}
    return solved


def _assert_close(actual, expected, tol=1e-6):
    assert abs(actual - expected) <= tol, f"Expected {expected}, got {actual}"


def test_milp_minimize_a_with_lower_bound():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=4)
        b = Model.IntegerVar(min=0, max=4)

        def objective_contribution(self):
            return self.a

    model = Model("milp-min-a")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(item.a >= 2)

    solved = _solve(model)
    _assert_close(solved.get_value(item.a), 2.0)


def test_milp_minimize_sum_with_upper_bounds():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=3)
        b = Model.IntegerVar(min=0, max=3)

        def objective_contribution(self):
            return self.a + self.b

    model = Model("milp-min-sum")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(item.a <= 3)
    model.constraints.append(item.b <= 3)

    solved = _solve(model)
    _assert_close(solved.get_value(item.a), 0.0)
    _assert_close(solved.get_value(item.b), 0.0)


def test_milp_maximize_with_equality_constraint():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=4)

        def objective_contribution(self):
            return self.a

    model = Model("milp-max-eq")
    model.objective_sense = "maximize"
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(item.a == 3)

    solved = _solve(model)
    _assert_close(solved.get_value(item.a), 3.0)


def test_milp_two_sided_constraint():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=3)
        b = Model.IntegerVar(min=0, max=3)

        def objective_contribution(self):
            return self.a + 2 * self.b

    model = Model("milp-two-sided")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(item.a + item.b >= 2)

    solved = _solve(model)
    a_val = solved.get_value(item.a)
    b_val = solved.get_value(item.b)
    assert a_val + b_val >= 2
    _assert_close(a_val + 2 * b_val, 2.0)


def test_milp_combined_linear_constraints():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=3)
        b = Model.IntegerVar(min=0, max=3)

        def objective_contribution(self):
            return self.a - self.b

    model = Model("milp-combined-linear")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(item.a >= 1)
    model.constraints.append(item.b <= 3)

    solved = _solve(model)
    _assert_close(solved.get_value(item.a), 1.0)
    _assert_close(solved.get_value(item.b), 3.0)


def test_milp_expression_with_coefficients():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=3)
        b = Model.IntegerVar(min=0, max=3)

        def objective_contribution(self):
            return 3 * self.a + 2 * self.b

    model = Model("milp-coeffs")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(2 * item.a + item.b >= 3)

    solved = _solve(model)
    a_val = solved.get_value(item.a)
    b_val = solved.get_value(item.b)
    assert 2 * a_val + b_val >= 3
    _assert_close(3 * a_val + 2 * b_val, 5.0)


def test_milp_both_sides_expression_equality():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=3)
        b = Model.IntegerVar(min=0, max=3)

        def objective_contribution(self):
            return self.a + self.b

    model = Model("milp-both-sides-eq")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(item.a + item.b == item.a + 1)

    solved = _solve(model)
    _assert_close(solved.get_value(item.b), 1.0)


def test_milp_both_sides_inequality():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=3)
        b = Model.IntegerVar(min=0, max=3)

        def objective_contribution(self):
            return self.a + self.b

    model = Model("milp-both-sides-ineq")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(2 * item.a + item.b <= 2 * item.a + item.b + 1)

    solved = _solve(model)
    _assert_close(solved.get_value(item.a), 0.0)
    _assert_close(solved.get_value(item.b), 0.0)


def test_milp_fractional_coefficients():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=4)

        def objective_contribution(self):
            return self.a

    model = Model("milp-fractional")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(0.5 * item.a + 1.5 <= 3)

    solved = _solve(model)
    _assert_close(solved.get_value(item.a), 0.0)


def test_milp_quadratic_binary_equality():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.BinaryVar()
        b = Model.BinaryVar()

        def objective_contribution(self):
            return self.a + self.b

    model = Model("milp-quad-bin-eq")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(Constraint(item.a * item.b, "==", 1))

    solved = _solve(model)
    _assert_close(solved.get_value(item.a), 1.0)
    _assert_close(solved.get_value(item.b), 1.0)


def test_milp_quadratic_binary_leq_zero():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.BinaryVar()
        b = Model.BinaryVar()

        def objective_contribution(self):
            return self.a + self.b

    model = Model("milp-quad-bin-leq")
    model.objective_sense = "maximize"
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(Constraint(item.a * item.b, "<=", 0))

    solved = _solve(model)
    a_val = solved.get_value(item.a)
    b_val = solved.get_value(item.b)
    assert a_val * b_val == 0
    _assert_close(a_val + b_val, 1.0)


def test_milp_quadratic_integer_integer():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=2)
        b = Model.IntegerVar(min=0, max=2)

        def objective_contribution(self):
            return self.a + self.b

    model = Model("milp-quad-int-int")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(Constraint(item.a * item.b, ">=", 2))

    solved = _solve(model)
    a_val = solved.get_value(item.a)
    b_val = solved.get_value(item.b)
    assert a_val * b_val >= 2
    _assert_close(a_val + b_val, 3.0)


def test_milp_quadratic_integer_binary():
    _ = pytest.importorskip("pyscipopt")

    class Item(Element):
        a = Model.IntegerVar(min=0, max=2)
        b = Model.BinaryVar()
        c = Model.IntegerVar(min=0, max=2)

        def objective_contribution(self):
            return self.a + self.c

    model = Model("milp-quad-int-bin")
    item = Item("i1")
    model.add_element(item)
    model.constraints.append(Constraint(item.a * item.b, "<=", item.c))
    model.constraints.append(item.b == 1)
    model.constraints.append(item.a >= 1)

    solved = _solve(model)
    a_val = solved.get_value(item.a)
    b_val = solved.get_value(item.b)
    c_val = solved.get_value(item.c)
    assert b_val == 1
    assert a_val >= 1
    assert a_val * b_val <= c_val
    _assert_close(c_val, a_val)
