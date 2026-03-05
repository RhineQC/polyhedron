from __future__ import annotations

# pylint: disable=protected-access

from datetime import timedelta
import time

import pytest


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    passed = len(terminalreporter.stats.get("passed", []))
    failed = len(terminalreporter.stats.get("failed", []))
    skipped = len(terminalreporter.stats.get("skipped", []))
    duration = 0.0
    session = terminalreporter._session
    if session is not None:
        duration = getattr(session, "duration", None)
        if duration is None:
            starttime = getattr(session, "starttime", None)
            if starttime is not None:
                duration = time.time() - starttime
        if duration is None:
            duration = 0.0
    terminalreporter.section("Test Report")
    terminalreporter.write_line(f"Passed: {passed}")
    terminalreporter.write_line(f"Failed: {failed}")
    terminalreporter.write_line(f"Skipped: {skipped}")
    terminalreporter.write_line(f"Duration: {timedelta(seconds=duration)}")
