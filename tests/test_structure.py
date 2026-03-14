def test_structure_imports():
    import polyhedron

    assert hasattr(polyhedron, "Model")
    assert hasattr(polyhedron, "Element")
    assert hasattr(polyhedron, "objective")
    assert hasattr(polyhedron, "minimize")
    assert hasattr(polyhedron, "maximize")
    assert hasattr(polyhedron, "flatten_weighted_objectives")
    assert hasattr(polyhedron, "lint_model")
    assert hasattr(polyhedron, "debug_infeasibility")
    assert hasattr(polyhedron, "explain_model")
    assert hasattr(polyhedron, "validate_model_units")
    assert hasattr(polyhedron, "ScenarioRunner")
    assert hasattr(polyhedron, "with_data_contract")
