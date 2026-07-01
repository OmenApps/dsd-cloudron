"""The test-tier status must stay visible even under `pytest -q` (how CI runs)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_tier_status_is_reported_under_quiet():
    # pytest_report_header is suppressed by -q, so the tier status is emitted from
    # pytest_terminal_summary instead. Run a small slice of the suite under -q in a
    # subprocess and confirm the status line still reaches stdout - otherwise a
    # skipped tier goes silent in CI and a green run hides zero coverage.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/unit_tests/test_docs_present.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert "dsd-cloudron test tiers:" in result.stdout
