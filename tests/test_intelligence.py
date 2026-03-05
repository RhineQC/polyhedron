from polyhedron.intelligence import HeuristicBase, SolverContext


class DummyHeuristic(HeuristicBase):
    def __init__(self):
        super().__init__(name="dummy")

    def apply(self, context: SolverContext):
        return None


def test_heuristic_run_tracks_calls():
    h = DummyHeuristic()
    ctx = SolverContext(model=object())
    h.run(ctx)
    assert h.stats.calls == 1
