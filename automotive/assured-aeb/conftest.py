"""Test wiring of the assured AEB WP-12 checks (offline only).

``XVERSE_PLATFORM_PROFILES`` names the platform profile-schema directory (``xdl/profiles`` of a ``git archive`` of the
X-Verse Lite rc.1 tag). The platform packages come from the interpreter's environment (the pinned test venv).
"""

import os
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


@pytest.fixture(scope="session")
def schema_paths():
    directory = os.environ.get("XVERSE_PLATFORM_PROFILES")
    if not directory:
        pytest.skip("XVERSE_PLATFORM_PROFILES is not set: platform-backed checks are skipped")
    import check_topology

    return check_topology.schemas(Path(directory))
