"""WP-13 #4b: the numpy image operations are bit-exact with the standard-library reference (review-wp13-imageops-np).

The bit-exact probe (``imageops_np_probe.py``) runs in the U2/U3 unit pattern, with the real CPython 3.13.13,
``-S -s -B`` and ``PYTHONPATH`` to the sensor venv's site-packages. That directory is named by
``XVERSE_AEB_SENSOR_SITE`` (no default; skipped without it). The selection and import checks need the standard library
only and always run.
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import types

import pytest

from assured_aeb import camera_chain as C
from assured_aeb import imageops as I

HERE = Path(__file__).resolve().parents[1]
PY313 = Path("/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13")
SITE = Path(os.environ["XVERSE_AEB_SENSOR_SITE"]) if os.environ.get("XVERSE_AEB_SENSOR_SITE") else None
needs_site = pytest.mark.skipif(not (SITE and (SITE / "numpy").is_dir() and PY313.is_file()),
                                reason="XVERSE_AEB_SENSOR_SITE does not name the sensor venv site-packages")


def _imports(path):
    tree = ast.parse(path.read_text())
    return {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} | \
        {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level == 0}


def test_reference_modules_import_no_numpy():
    for name in ("imageops", "camera_chain", "radar_zone", "checks"):
        assert "numpy" not in _imports(HERE / "assured_aeb" / f"{name}.py"), name


def test_port_imports_only_numpy_and_the_standard_library():
    assert _imports(HERE / "assured_aeb" / "imageops_np.py") == {"__future__", "math", "numpy"}


def test_selection_accepts_only_the_two_implementations():
    assert C._ops(None) is I and C._ops(I) is I
    fake = types.ModuleType("assured_aeb.imageops_np")
    assert C._ops(fake) is fake  # selected by module identity name; the real module needs numpy (sensor venv)
    for bad in (types.ModuleType("numpy"), object(), "imageops_np"):
        with pytest.raises(TypeError):
            C._ops(bad)


@needs_site
def test_probe_is_bit_exact_in_the_unit_pattern():
    env = {"PATH": "/usr/bin", "HOME": "/nonexistent-sensor-home", "PYTHONDONTWRITEBYTECODE": "1", "OMP_NUM_THREADS": "1",
           "OPENBLAS_NUM_THREADS": "1", "PYTHONPATH": f"{SITE}:{HERE}"}
    result = subprocess.run([str(PY313), "-S", "-s", "-B", str(HERE / "tests" / "imageops_np_probe.py")], env=env,
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads(result.stdout)
    assert summary["failures"] == [] and summary["comparisons"] > 1000
    assert summary["numpy"] == "2.5.4" and summary["numpyFile"].startswith(str(SITE)) and summary["siteImported"] is False
