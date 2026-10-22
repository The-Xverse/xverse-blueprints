"""Host harness wiring: the platform's owned trusted-host Maestro fixtures, imported from the exported
accepted platform source (``XVERSE_PLATFORM_SRC``, ``git archive`` of xverse-platform main). These are the
fixtures the platform uses for its own real-child runtime verification ("private owned component-test
harness, not runtime C1"); using them here is non-M1 integration evidence (DLG-7)."""

import os
import sys
from pathlib import Path

PLATFORM_SRC = Path(os.environ["XVERSE_PLATFORM_SRC"]).resolve()
sys.path.insert(0, str(PLATFORM_SRC))

from tests.thesis_lite.maestro.test_affa_native import authority_binary  # noqa: E402,F401
from tests.thesis_lite.maestro.test_boundary import environment  # noqa: E402,F401
from tests.thesis_lite.maestro.test_launcher import binaries  # noqa: E402,F401
from tests.thesis_lite.maestro.test_run_bootstrap import run_bootstrap_binary  # noqa: E402,F401
