"""S5 — highspy version matches the pin (spec §15, §16 rule #4).

V3 was written against the 1.7.x addCols / addRow signatures but the install
pulled 1.14.0 (signatures had changed) and the solver crashed before solving.

If a future build genuinely needs newer highspy, the migration is:
  1. Update requirements.txt to the new pin.
  2. Audit every addCol / addRow / setOptionValue / changeColIntegrality call
     in backend/methods/*.py against the new version's API.
  3. Update this test's expected version string.
"""
from __future__ import annotations

import pytest


EXPECTED_HIGHSPY_VERSION = "1.7.2"


def test_highspy_version_matches_requirements():
    try:
        import importlib.metadata as _md
        actual = _md.version("highspy")
    except Exception:
        # Fallback for older pkg_resources path (some envs lack importlib.metadata at runtime)
        import pkg_resources
        actual = pkg_resources.get_distribution("highspy").version

    assert actual == EXPECTED_HIGHSPY_VERSION, (
        f"highspy {actual} installed but requirements.txt pins {EXPECTED_HIGHSPY_VERSION}. "
        "If intentionally migrated, update this test AND verify every "
        "addCol / addRow / setOptionValue / changeColIntegrality call in "
        "backend/methods/*.py against the new version's API."
    )
