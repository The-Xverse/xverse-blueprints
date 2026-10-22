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
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PY310 = "/usr/bin/python3.10"
PY313 = "/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13"
CARLA_ENV = "/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310"
DRIVER_VENV = "/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0/.x-verse-build/cache/xverse-lite-live-20261022/driver-venv"
LEGACY_VCU = "/home/jefferson/autoverse/vecu/vcu_zenoh/src"
ROUTER = "tcp/127.0.0.1:7447"


@dataclass(frozen=True)
class Unit:
    name: str
    executable: str
    arguments: tuple
    working_directory: str
    environment: dict = field(default_factory=dict)
    owned: bool = True


def units(*, compat: Path, run_dir: Path, work: Path, socket_path: str, plan: Path | None, episode_s: float = 14.0,
          pause_after_s: float | None = None) -> list[Unit]:
    """Return the four units for one run (paths are absolute)."""

    src = str(compat / "src")
    descriptors = str(compat / "xdl/descriptors/aeb-sim/carla-sensors.json")
    scenario = str(compat / "xdl/descriptors/aeb-sim/live-scenario.json")
    site = CARLA_ENV + "/lib/python3.10/site-packages"
    driver_path = DRIVER_VENV + "/lib/python3.13/site-packages:" + src
    driver = ("-B", "-m", "xverse_compat.live.driver", "--socket", socket_path, "--descriptors", descriptors, "--router", ROUTER,
              "--run-dir", str(run_dir / "driver"), "--episode-s", str(episode_s), "--accept-timeout-s", "12", "--wall-bound-s", "60",
              "--marker", str(work / "lite-driver-binding.marker"), "--linger", "--stderr", str(run_dir / "lite-driver.err")) + (("--plan", str(plan)) if plan else ())         + (("--pause-after-s", str(pause_after_s)) if pause_after_s is not None else ())
    return [
        Unit("lite-driver", PY313, driver, src, {"PATH": "/usr/bin", "HOME": str(run_dir / "home"), "PYTHONPATH": driver_path}),
        Unit("carla-adapter", PY310,
             ("-s", "-B", "-m", "xverse_compat_carla.main", "--protocol", "2", "--connect", "unix:" + socket_path,
              "--connect-timeout-s", "20", "--source", "live:127.0.0.1:2000:scenario", "--scenario", scenario,
              "--descriptors", descriptors, "--carla-site", site, "--marker", str(work / "carla-adapter-binding.marker"), "--linger", "--stderr", str(run_dir / "carla-adapter.err")),
             src, {"PATH": "/usr/bin", "HOME": str(run_dir / "carla-home")}),
        Unit("legacy-vcu", PY310, ("-B", "main.py"), LEGACY_VCU, {"PATH": "/usr/bin", "HOME": "/home/jefferson"}, owned=False),
        Unit("driver-stimulus", PY313,
             ("-B", "-m", "xverse_compat.live.stimulus", "--router", ROUTER, "--out", str(run_dir / "stimulus.jsonl"),
              "--marker", str(work / "driver-stimulus-binding.marker"), "--linger", "--stderr", str(run_dir / "driver-stimulus.err")),
             src, {"PATH": "/usr/bin", "HOME": str(run_dir / "home"), "PYTHONPATH": driver_path}),
    ]
