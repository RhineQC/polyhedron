from polyhedron.performance import ModelTimings, timing


def test_timing_context_records_duration():
    timings = ModelTimings()
    with timing(timings, "section"):
        pass
    assert "section" in timings.sections
    assert timings.sections["section"] >= 0.0
