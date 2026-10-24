"""Units of the Lite CARLA closed-loop blueprint (Phase 7 live integration; engineering only).

Four Maestro units, started in this order (each depends on the previous one):

1. ``lite-driver``: owned; the platform side of ``carla-items/2`` and the gateway to the legacy VCU;
2. ``carla-adapter``: owned; the pinned CPython 3.10 CARLA client adapter, the single tick owner and
   actuator writer, owning the declared ego vehicle and sensors;
3. ``legacy-vcu``: the unchanged legacy VCU (``autoverse/vecu/vcu_zenoh@125566e``, ``main.py``);
4. ``driver-stimulus``: owned; the declared pedal profile that replaces the human driver.

Executables are real ELF interpreters (Maestro seals them; a symlinked venv interpreter cannot be
sealed): ``/usr/bin/python3.10`` and the pyenv CPython 3.13.13 binary. The pinned carla environment is
added with ``--carla-site``; the driver environment with ``PYTHONPATH``.

S1c-2 part 2 (S1c finding 40, platform S1b): each owned unit runs in its own working directory
``work/<unit>/``, inside the collection source root, where it answers the native nonce-marker readiness
challenge (``xverse_compat.live.readiness``). The adapter therefore gets ``PYTHONPATH`` to the compat ``src``.
Unit stderr is captured by the platform into private run-scoped files, so the units get no ``--stderr``.
The legacy VCU is unchanged: not owned, its own checkout as working directory, liveness-only readiness.
``XVERSE_LIVE_DRIVER_VENV`` (exported by ``run-live.sh``) selects the driver venv; the default is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path

PY310 = "/usr/bin/python3.10"
PY313 = "/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13"
CARLA_ENV = "/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310"
DRIVER_VENV = "/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-lite-live-20261022/driver-venv"
LEGACY_VCU = "/home/jefferson/autoverse/vecu/vcu_zenoh/src"
ROUTER = "tcp/127.0.0.1:7447"
OWNED = ("lite-driver", "carla-adapter", "driver-stimulus")


def driver_venv() -> str:
    """The driver venv of this run: ``XVERSE_LIVE_DRIVER_VENV`` (run-live.sh), else the pinned default."""

    return os.environ.get("XVERSE_LIVE_DRIVER_VENV") or DRIVER_VENV


@dataclass(frozen=True)
class Unit:
    name: str
    executable: str
    arguments: tuple
    working_directory: str
    environment: dict = field(default_factory=dict)
    owned: bool = True


def units(*, compat: Path, run_dir: Path, work: Path, socket_path: str, plan: Path | None, episode_s: float = 14.0,
          pause_after_s: float | None = None, stimulus_profile: str = "standard") -> list[Unit]:
    """Return the four units for one run (paths are absolute); creates each owned unit's ``work/<unit>/``."""

    src = str(compat / "src")
    descriptors = str(compat / "xdl/descriptors/aeb-sim/carla-sensors.json")
    scenario = str(compat / "xdl/descriptors/aeb-sim/live-scenario.json")
    site = CARLA_ENV + "/lib/python3.10/site-packages"
    driver_path = driver_venv() + "/lib/python3.13/site-packages:" + src
    cwd = {name: work / name for name in OWNED}
    for path in cwd.values():
        path.mkdir()  # fresh and empty: a stale .xverse-ready fails the probe admission (ML-RUN-PROBE-STALE)
    driver = ("-B", "-m", "xverse_compat.live.driver", "--socket", socket_path, "--descriptors", descriptors, "--router", ROUTER,
              "--run-dir", str(run_dir / "driver"), "--episode-s", str(episode_s), "--accept-timeout-s", "12", "--wall-bound-s", "60",
              "--marker", str(work / "lite-driver-binding.marker"), "--linger") + (("--plan", str(plan)) if plan else ())         + (("--pause-after-s", str(pause_after_s)) if pause_after_s is not None else ())
    return [
        Unit("lite-driver", PY313, driver, str(cwd["lite-driver"]), {"PATH": "/usr/bin", "HOME": str(run_dir / "home"), "PYTHONPATH": driver_path}),
        Unit("carla-adapter", PY310,
             ("-s", "-B", "-m", "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:" + socket_path,
              "--connect-timeout-s", "20", "--source", "live:127.0.0.1:2000:scenario", "--scenario", scenario,
              "--descriptors", descriptors, "--carla-site", site, "--owned-registry", str(run_dir / "owned-actors.json"),
              "--marker", str(work / "carla-adapter-binding.marker"), "--linger"),
             str(cwd["carla-adapter"]), {"PATH": "/usr/bin", "HOME": str(run_dir / "carla-home"), "PYTHONPATH": src}),
        Unit("legacy-vcu", PY310, ("-B", "main.py"), LEGACY_VCU, {"PATH": "/usr/bin", "HOME": "/home/jefferson"}, owned=False),
        Unit("driver-stimulus", PY313,
             ("-B", "-m", "xverse_compat.live.stimulus", "--router", ROUTER, "--out", str(run_dir / "stimulus.jsonl"),
              "--marker", str(work / "driver-stimulus-binding.marker"), "--linger")
             + (("--profile", stimulus_profile) if stimulus_profile != "standard" else ()),  # S1 FR-018 long-run
             str(cwd["driver-stimulus"]), {"PATH": "/usr/bin", "HOME": str(run_dir / "home"), "PYTHONPATH": driver_path}),
    ]
