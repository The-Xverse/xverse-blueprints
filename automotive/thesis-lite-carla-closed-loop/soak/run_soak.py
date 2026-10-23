"""Predeclared S1d soak runner (thesis 029 plan.md, Soak; FR-019, FR-020; S-D4, S-D6).

    python3 run_soak.py --compat <clean detached compat worktree> --blueprints <clean detached blueprints worktree>
                        --out <soak dir> [--dry-run]

Protocol, fixed before the first run (FR-019):
- Revisions: the given checkouts must be clean and detached; their HEADs (and the platform export revision) are
  recorded and re-checked before every run. Any change stops the soak (FR-020).
- Cases: nominal, freeze-vcu, cancel-paused and long-run 30 each (rate-bound), baseline 10, no-carla 10 (smoke).
  30 rounds; each round runs one of each rate-bound case, plus a baseline in every third round, in an order
  rotated per round so that time and host drift do not line up with a case. no-carla needs the server stopped, so
  its 10 runs are made in the four server-stopped gaps (before the first block, between blocks, after the last
  block: 3, 3, 2, 2). This is the declared realization of "interleaved rounds" for that smoke case.
- CARLA: one server instance per block of 10 rounds, started with the author's recipe
  (``just server-nvidia Epic 2000`` in ~/autoverse) and stopped between blocks.
- Health: an independent read-only check (health_check.py) before the preflight and after the cleanup of every
  CARLA run. A failed check makes that run INVALID; the server is restarted and the run repeated once at the end of
  its block. More than 3 server failures stop the soak.
- Load: a round starts only at a 1-minute load <= 5; the load is sampled every 5 s during each run. A passing run
  whose sampled maximum exceeds 10 is an observation (not counted; repeated once at the end of the soak). A failure
  stops the soak whatever the load.
- Criteria: audit.py per run (P1, P3-P8; P2 an observation). The first failure stops the soak; a finding is
  recorded before any repair and a repaired soak restarts from zero (FR-020).
- Validity: if observation plus INVALID runs exceed 10% of a case's scheduled runs, the soak is INVALID.
Writes ``soak-manifest.json`` (append-only run list) and, at the end, ``soak-report.json``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit  # noqa: E402

L10 = Path("/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0")
CARLA_SITE = L10 / ".x-verse-build/cache/xverse-compat-carla-0.9.15-cp310/lib/python3.10/site-packages"
PLATFORM_SRC = L10 / ".x-verse-build/cache/xverse-lite-live-20261022/platform-src"
AUTOVERSE = Path.home() / "autoverse"
RATE_CASES = ("nominal", "freeze-vcu", "cancel-paused", "long-run")
ROUNDS, BLOCK, BASELINE_EVERY = 30, 10, 3
NO_CARLA_GAPS = (3, 3, 2, 2)
LOAD_START_MAX, LOAD_RUN_MAX, LOAD_PERIOD_S = 5.0, 10.0, 5.0
MAX_SERVER_FAILURES, INVALID_SHARE = 3, 0.10


def schedule() -> list[dict]:
    """The predeclared run order: CARLA blocks of rounds and the server-stopped gaps with their no-carla runs."""
    plan, gap = [], 0
    for block in range(ROUNDS // BLOCK):
        plan.append({"kind": "gap", "noCarla": NO_CARLA_GAPS[gap]})
        gap += 1
        rounds = []
        for r in range(block * BLOCK, (block + 1) * BLOCK):
            order = list(RATE_CASES[r % 4:] + RATE_CASES[:r % 4])
            if r % BASELINE_EVERY == BASELINE_EVERY - 1:
                order.insert(r % (len(order) + 1), "baseline")
            rounds.append({"round": r + 1, "cases": order})
        plan.append({"kind": "block", "block": block + 1, "rounds": rounds})
    plan.append({"kind": "gap", "noCarla": NO_CARLA_GAPS[gap]})
    return plan


def _git(path: Path, *args) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def identities(compat: Path, blueprints: Path) -> dict:
    out = {}
    for name, path in (("compat", compat), ("blueprints", blueprints)):
        status = _git(path, "status", "--porcelain")
        branch = subprocess.run(["git", "-C", str(path), "symbolic-ref", "-q", "HEAD"], capture_output=True, text=True).stdout.strip()
        out[name] = {"path": str(path), "head": _git(path, "rev-parse", "HEAD"), "clean": status == "", "detached": branch == ""}
    try:
        out["platformSrc"] = (PLATFORM_SRC / ".export-revision").read_text().strip()
    except OSError:
        out["platformSrc"] = None
    return out


def load1() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


class LoadSampler:
    def __init__(self):
        self.samples, self._stop = [], threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            self.samples.append({"monotonicNs": time.monotonic_ns(), "load1": load1()})
            self._stop.wait(LOAD_PERIOD_S)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(LOAD_PERIOD_S + 1)
        self.samples.append({"monotonicNs": time.monotonic_ns(), "load1": load1()})


def health(home: Path) -> dict:
    home.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(["env", "-i", "PATH=/usr/bin", f"HOME={home}", "/usr/bin/python3.10", "-s", "-B",
                           str(HERE / "health_check.py"), "--carla-site", str(CARLA_SITE)],
                          capture_output=True, text=True, timeout=60, cwd="/tmp")
    try:
        result = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        result = {"healthy": False, "error": "no JSON", "stderr": done.stderr[-500:]}
    result["exit"] = done.returncode
    result["healthy"] = bool(result.get("healthy")) and done.returncode == 0
    return result


def carla_pids() -> list[int]:
    out = subprocess.run(["ps", "-eo", "pid=,comm="], capture_output=True, text=True).stdout.splitlines()
    return [int(line.split()[0]) for line in out if len(line.split()) > 1 and line.split()[1].startswith("CarlaUE4-Linux")]


def port_listening(port: int) -> bool:
    return f":{port} " in subprocess.run(["ss", "-tln"], capture_output=True, text=True).stdout


def start_server(out: Path, home: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    (out / "started-at.txt").write_text(time.strftime("%Y-%m-%dT%H:%M:%S%z") + "\n")
    with open(out / "server.out.log", "w") as so, open(out / "server.err.log", "w") as se:
        subprocess.Popen(["setsid", "just", "server-nvidia", "Epic", "2000"], cwd=AUTOVERSE, stdout=so, stderr=se,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    end = time.monotonic() + 180
    while time.monotonic() < end and not port_listening(2000):
        time.sleep(3)
    gpu_end = time.monotonic() + 200
    while time.monotonic() < gpu_end:
        used = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True).stdout.strip().splitlines()
        if used and int(used[0]) > 5000:
            break
        time.sleep(5)
    time.sleep(40)  # the recipe's warm-up, as in every Phase 7 and S1 run
    check = health(home)
    (out / "initial-health.json").write_text(json.dumps(check, sort_keys=True) + "\n")
    return check


def stop_server(out: Path) -> None:
    for pid in carla_pids():
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
    end = time.monotonic() + 30
    while carla_pids() and time.monotonic() < end:
        time.sleep(1)
    for pid in carla_pids():  # a server that ignores TERM (instance 6, Phase 7) is killed and recorded
        os.kill(pid, 9)
        (out / "killed.txt").write_text(f"SIGKILL {pid}\n")
    (out / "stopped-at.txt").write_text(time.strftime("%Y-%m-%dT%H:%M:%S%z") + "\n")


class Soak:
    def __init__(self, compat: Path, blueprints: Path, out: Path):
        self.compat, self.blueprints, self.out = compat, blueprints, out
        self.script_dir = blueprints / "automotive/thesis-lite-carla-closed-loop"
        self.manifest = out / "soak-manifest.json"
        self.pinned = identities(compat, blueprints)
        self.runs, self.server_failures, self.server_index = [], 0, 0
        self.home = out / "carla-home"

    def _save(self, state="running", stop_reason=None):
        self.manifest.write_text(json.dumps({"protocol": "thesis 029 plan.md Soak (S-D4); runner " + str(Path(__file__).name),
                                             "pinned": self.pinned, "schedule": schedule(), "state": state,
                                             "stopReason": stop_reason, "serverFailures": self.server_failures,
                                             "runs": self.runs}, indent=1, sort_keys=True) + "\n")

    def _check_pins(self):
        now = identities(self.compat, self.blueprints)
        if now != self.pinned or not all(now[k]["clean"] and now[k]["detached"] for k in ("compat", "blueprints")):
            raise SystemExit(self._stop("revision or tree changed, or not clean and detached (FR-020)", now))

    def _stop(self, reason, detail=None):
        self.runs.append({"stop": reason, "detail": detail})
        self._save("stopped", reason)
        return 2

    def _wait_load(self):
        waited = 0
        while load1() > LOAD_START_MAX:
            time.sleep(15)
            waited += 15
        return waited

    def run_one(self, case: str, *, carla: bool) -> dict:
        self._check_pins()
        stamp = time.strftime("%Y%m%dT%H%M%S")
        run_dir = self.out / ("baseline-" + stamp if case == "baseline" else f"lite-{stamp}-{case}")
        entry = {"case": case, "run": run_dir.name, "server": self.server_index if carla else None}
        if carla:
            entry["healthBefore"] = health(self.home)
        env = dict(os.environ, XVERSE_COMPAT_SRC=str(self.compat))
        command = ([str(self.script_dir / "run-baseline.sh"), str(run_dir)] if case == "baseline"
                   else [str(self.script_dir / "run-live.sh"), case, str(run_dir)])
        with LoadSampler() as sampler:
            began = time.monotonic()
            done = subprocess.run(["timeout", "900"] + command, env=env, capture_output=True, text=True)
            entry["durationS"] = round(time.monotonic() - began, 1)
        (run_dir.parent / (run_dir.name + ".console")).write_text(done.stdout + done.stderr)
        entry["scriptExit"] = done.returncode
        entry["loadSamples"] = sampler.samples
        entry["loadMax"] = max(s["load1"] for s in sampler.samples)
        if carla:
            entry["healthAfter"] = health(self.home)
        verdict = audit.audit(run_dir) if run_dir.exists() else {"pass": False, "failedChecks": ["run directory missing"]}
        entry["audit"] = {"pass": verdict["pass"], "failedChecks": verdict["failedChecks"]}
        (run_dir / "soak-audit.json").write_text(json.dumps(verdict, indent=1, sort_keys=True, default=str) + "\n") if run_dir.exists() else None
        invalid = carla and not (entry["healthBefore"]["healthy"] and entry["healthAfter"]["healthy"])
        entry["status"] = ("INVALID" if invalid else "FAIL" if not verdict["pass"]
                           else "OBSERVATION" if entry["loadMax"] > LOAD_RUN_MAX else "PASS")
        self.runs.append(entry)
        self._save()
        return entry

    def execute(self, dry_run=False) -> int:
        self.out.mkdir(parents=True, exist_ok=True)
        if not all(self.pinned[k]["clean"] and self.pinned[k]["detached"] for k in ("compat", "blueprints")):
            print("refused: the compat and blueprints checkouts must be clean and detached", file=sys.stderr)
            return 4
        if dry_run:
            print(json.dumps({"pinned": self.pinned, "schedule": schedule()}, indent=1))
            return 0
        if carla_pids() or port_listening(2000):
            print("refused: a CARLA server is already running; the soak owns the server lifecycle", file=sys.stderr)
            return 4
        self._save()
        repeats_end = []
        for item in schedule():
            if item["kind"] == "gap":
                for _ in range(item["noCarla"]):
                    self._wait_load()
                    entry = self.run_one("no-carla", carla=False)
                    if entry["status"] == "FAIL":
                        return self._stop(f"criterion failure in {entry['run']} (FR-020)")
                    if entry["status"] == "OBSERVATION":
                        repeats_end.append(("no-carla", False))
                continue
            self.server_index += 1
            server_dir = self.out / f"carla-server-{self.server_index}"
            if not start_server(server_dir, self.home)["healthy"]:
                self.server_failures += 1
                stop_server(server_dir)
                if self.server_failures > MAX_SERVER_FAILURES:
                    return self._stop("more than 3 server failures")
                self.server_index += 1
                server_dir = self.out / f"carla-server-{self.server_index}"
                if not start_server(server_dir, self.home)["healthy"]:
                    return self._stop("server failed to start twice")
            block_repeats = []
            for rnd in item["rounds"]:
                waited = self._wait_load()
                self.runs.append({"round": rnd["round"], "loadWaitS": waited, "cases": rnd["cases"]})
                for case in rnd["cases"]:
                    entry = self.run_one(case, carla=True)
                    if entry["status"] == "FAIL":
                        stop_server(server_dir)
                        return self._stop(f"criterion failure in {entry['run']} (FR-020)")
                    if entry["status"] == "INVALID":
                        self.server_failures += 1
                        stop_server(server_dir)
                        if self.server_failures > MAX_SERVER_FAILURES:
                            return self._stop("more than 3 server failures")
                        self.server_index += 1
                        server_dir = self.out / f"carla-server-{self.server_index}"
                        start_server(server_dir, self.home)
                        block_repeats.append(case)
                    elif entry["status"] == "OBSERVATION":
                        repeats_end.append((case, True))
            for case in block_repeats:  # an INVALID run is repeated once, at the end of its block
                entry = self.run_one(case, carla=True)
                entry["repeatOf"] = "INVALID"
                if entry["status"] == "FAIL":
                    stop_server(server_dir)
                    return self._stop(f"criterion failure in {entry['run']} (FR-020)")
            stop_server(server_dir)
        if repeats_end:  # observation repeats, once each, at the end of the soak
            self.server_index += 1
            server_dir = self.out / f"carla-server-{self.server_index}"
            carla_needed = any(c for _, c in repeats_end)
            if carla_needed:
                start_server(server_dir, self.home)
            for case, carla in sorted(repeats_end, key=lambda x: not x[1]):
                if not carla and carla_pids():
                    stop_server(server_dir)
                self._wait_load()
                entry = self.run_one(case, carla=carla)
                entry["repeatOf"] = "OBSERVATION"
                if entry["status"] == "FAIL":
                    stop_server(server_dir)
                    return self._stop(f"criterion failure in {entry['run']} (FR-020)")
            stop_server(server_dir)
        report = summarize(self.runs)
        (self.out / "soak-report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
        self._save("complete")
        return 0 if report["valid"] else 3


def upper_bound(n: int) -> float | None:
    """Exact one-sided 95% upper bound with zero failures, 1 - 0.05^(1/n) (plan.md, Interpretation)."""
    return round(1 - 0.05 ** (1 / n), 4) if n else None


def summarize(runs: list[dict]) -> dict:
    entries = [r for r in runs if "case" in r]
    by_case = {}
    for e in entries:
        by_case.setdefault(e["case"], []).append(e)
    scheduled = {"nominal": 30, "freeze-vcu": 30, "cancel-paused": 30, "long-run": 30, "baseline": 10, "no-carla": 10}
    out, valid = {"cases": {}}, True
    for case, items in by_case.items():
        passed = [e for e in items if e["status"] == "PASS"]
        excluded = [e for e in items if e["status"] in ("INVALID", "OBSERVATION")]
        share = len(excluded) / scheduled.get(case, len(items))
        valid = valid and share <= INVALID_SHARE and not any(e["status"] == "FAIL" for e in items)
        out["cases"][case] = {"runs": len(items), "valid": len(passed), "invalid": sum(e["status"] == "INVALID" for e in items),
                              "observations": sum(e["status"] == "OBSERVATION" for e in items),
                              "failures": sum(e["status"] == "FAIL" for e in items), "excludedShare": round(share, 3),
                              "upperBound95": upper_bound(len(passed)) if case in RATE_CASES else None}
    pooled = sum(out["cases"].get(c, {}).get("valid", 0) for c in RATE_CASES)
    out["pooledRateCases"] = {"valid": pooled, "upperBound95": upper_bound(pooled)}
    out["valid"] = valid
    out["note"] = ("engineering statement under the recorded conditions only; runs in a server block share server and host "
                   "state and are not fully independent trials (plan.md, Interpretation)")
    return out


def dispersion(run_dirs: list[Path]) -> dict:
    """P2 (an observation): min, max and standard deviation per case of the predeclared quantities."""
    values = {}
    for run in run_dirs:
        verdict = audit.audit(run)
        p2 = (verdict["observations"] or {}).get("P2")
        if not p2:
            continue
        obs, rt = p2.get("observer") or {}, p2.get("runtime") or {}
        row = {"peakKmh": obs.get("peakKmh"), "standstillAfterOnsetS": obs.get("standstillAfterOnsetS"),
               "distanceM": obs.get("distanceM"), "throttleSimS": (rt.get("commandedThrottle") or {}).get("simDurationS")}
        for key, value in row.items():
            if isinstance(value, (int, float)) and not math.isnan(value):
                values.setdefault(verdict["case"], {}).setdefault(key, []).append(value)
    return {case: {k: {"n": len(v), "min": min(v), "max": max(v), "stdev": round(statistics.pstdev(v), 4)}
                   for k, v in quantities.items()} for case, quantities in values.items()}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compat", type=Path, required=True)
    parser.add_argument("--blueprints", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dispersion", nargs="*", type=Path, help="report P2 over these run directories and exit")
    args = parser.parse_args(argv)
    if args.dispersion is not None:
        print(json.dumps(dispersion(args.dispersion), indent=1, sort_keys=True))
        return 0
    return Soak(args.compat.resolve(), args.blueprints.resolve(), args.out.resolve()).execute(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
