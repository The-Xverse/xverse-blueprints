"""Evidence report for the Lite CARLA closed-loop integration (Phase 7; engineering only).

Usage: ``python report.py --out DIR RUN_DIR...`` (baseline-* and lite-* run directories).

Motion metrics come from the passive evaluation observer (the same instrument in every run) and, for Lite
runs, also from the runtime motion items. Braking is judged from velocity and forward acceleration, never
from the command echo. Every raw file is listed with its SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _hashes(run: Path) -> dict:
    out = {}
    for path in sorted(run.rglob("*")):
        if path.is_file() and "pytest" not in path.parts and path.stat().st_size < 64 << 20:
            out[str(path.relative_to(run))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


DECEL_ONSET_MPS2 = -2.0
NOTES = ["Peak forward decelerations near -25 m/s^2 (~2.6 g) are CARLA vehicle-physics outputs under full braking at the "
         "simulator step, not a calibrated braking claim.",
         "The observer and the Lite runtime motion items both read CARLA snapshot velocity/acceleration: their agreement is "
         "the same source read twice, not an independent cross-check (review 1 R-17).",
         "Command echo (cachedControl) is never used as braking evidence; onset is measured from deceleration."]


def _brake_metrics(rows, t, speed, brake, accel):
    """rows sorted by time; peak speed, deceleration onset (first frame after the peak below DECEL_ONSET_MPS2),
    time to standstill, min forward acceleration; the brake-command/echo onset is reported separately."""

    if not rows:
        return {}
    peak = max(rows, key=speed)
    onset = next((r for r in rows if t(r) >= t(peak) and accel(r) < DECEL_ONSET_MPS2), None)
    command = next((r for r in rows if brake(r) > 0 and t(r) >= t(peak) - 0.5), None)
    stop = next((r for r in rows if onset is not None and t(r) >= t(onset) and speed(r) < 0.14), None)  # < 0.5 km/h
    window = [r for r in rows if onset is not None and t(r) >= t(onset) and (stop is None or t(r) <= t(stop))]
    return {"peakKmh": round(speed(peak) * 3.6, 2), "peakAtS": round(t(peak), 3),
            "brakeOnsetS": round(t(onset), 3) if onset else None, "speedAtOnsetKmh": round(speed(onset) * 3.6, 2) if onset else None,
            "standstillAfterOnsetS": round(t(stop) - t(onset), 3) if onset and stop else None,
            "minAccelForwardMps2": round(min(accel(r) for r in window), 3) if window else None,
            "brakeSignalOnsetS": round(t(command), 3) if command else None,
            "meanDecelMps2": round(speed(onset) / (t(stop) - t(onset)), 3) if onset and stop and t(stop) > t(onset) else None,
            "finalKmh": round(speed(rows[-1]) * 3.6, 3)}


def observer_metrics(run: Path) -> dict:
    rows = [r for r in _jsonl(run / "observer.jsonl") if r.get("ego")]
    if not rows:
        return {"framesWithEgo": 0}
    t0 = rows[0]["elapsedS"]
    moving = [r for r in rows if r["ego"]["speedMps"] > 0.05]
    m = _brake_metrics(rows, lambda r: r["elapsedS"] - t0, lambda r: r["ego"]["speedMps"], lambda r: r["ego"]["cachedControl"]["brake"],
                       lambda r: r["ego"]["accelForwardMps2"])
    deltas = [r["deltaS"] for r in rows]
    throttle = [r for r in rows if r["ego"]["cachedControl"]["throttle"] > 0]
    if throttle:  # the control the vehicle actually holds (legacy: VCU command / 1.2 damping)
        m["actuatedThrottle"] = {"max": round(max(r["ego"]["cachedControl"]["throttle"] for r in throttle), 4),
                                 "simDurationS": round(throttle[-1]["elapsedS"] - throttle[0]["elapsedS"], 3)}
    m.update(framesWithEgo=len(rows), spawnLocation=rows[0]["ego"]["location"],
             distanceM=round(math.dist(rows[0]["ego"]["location"], rows[-1]["ego"]["location"]), 2),
             simDeltaS={"mean": round(sum(deltas) / len(deltas), 5), "min": round(min(deltas), 5), "max": round(max(deltas), 5)},
             movingFrames=len(moving), timeBase="observer frames, simulation seconds since the ego first appeared")
    return m


def runtime_metrics(run: Path) -> dict:
    ticks = [r for r in _jsonl(run / "driver" / "driver-ticks.jsonl") if r.get("kind") == "tick" and r.get("motion")]
    if not ticks:
        return {}
    m = _brake_metrics(ticks, lambda r: r["simS"], lambda r: r["motion"]["speedMps"], lambda r: r["brake"], lambda r: r["motion"]["accelForwardMps2"])
    stale = [r for r in ticks if r["commandMeta"]["stale"]]
    windows, prev = [], None
    for r in ticks:
        if r["commandMeta"]["stale"] and (prev is None or not prev["commandMeta"]["stale"]):
            windows.append([r["simS"], r["simS"]])
        if r["commandMeta"]["stale"]:
            windows[-1][1] = r["simS"]
        prev = r
    th = [r for r in ticks if r["throttle"] > 0]
    if th:
        m["commandedThrottle"] = {"max": max(r["throttle"] for r in th), "simDurationS": round(th[-1]["simS"] - th[0]["simS"] + 0.05, 3),
                                  "firstMonotonicNs": th[0]["sentMonotonicNs"], "lastMonotonicNs": th[-1]["sentMonotonicNs"]}
    m.update(ticks=len(ticks), staleTicks=len(stale), staleWindowsS=[[round(a, 2), round(b, 2)] for a, b in windows],
             maxVcuCommandAgeMs=max((r["commandMeta"]["throttleAgeMs"] or 0) for r in ticks), timeBase="carla-simulation, seconds since the first ticked frame")
    return m


def run_summary(run: Path) -> dict:
    out = {"run": run.name, "path": str(run)}
    maestro = run / "maestro-run.json"
    if maestro.exists():
        r = json.loads(maestro.read_text())
        steps = r.get("steps") or []
        out["maestro"] = {k: r.get(k) for k in ("case", "nonM1", "executionSucceeded", "cleanupComplete", "dispatchDiagnostic", "diagnostics",
                                               "normalUnitRecordsComplete", "workArtifacts", "budgets", "cancelEpoch")}
        out["maestro"]["wallS"] = round((r["monotonicEndNs"] - r["monotonicStartNs"]) / 1e9, 2) if "monotonicEndNs" in r else None
        out["maestro"]["steps"] = {s["step_id"]: s["disposition"] for s in steps}
        m3 = list(run.glob("maestro-tmp/*/argus-maestro/events.jsonl"))
        faults = []
        if m3:
            for line in m3[0].read_text().splitlines():
                e = json.loads(line)
                x = e.get("extensions", {}).get("xverse.maestro", {})
                if x.get("faultId"):
                    faults.append({"phase": x.get("phase"), "outcome": x.get("outcome"), "hostS": e["clocks"]["host"]["value"],
                                   "tick": e["clocks"].get("simulation", {}).get("value")})
        out["maestro"]["faultEvents"] = faults
        if "cancelRequestedMonotonicNs" in r:
            out["maestro"]["cancelToRunEndS"] = round((r["monotonicEndNs"] - r["cancelRequestedMonotonicNs"]) / 1e9, 3)
        out["kind"] = "lite"
    else:
        out["kind"] = "baseline"
    for name in ("driver/driver-summary.json",):
        path = run / name
        if path.exists():
            s = json.loads(path.read_text())
            out["driver"] = {k: s.get(k) for k in ("ticks", "endReason", "flowVerdicts", "vcuStaleTicks", "error", "done")}
    for name in ("restore-guard.json", "world-after.json"):
        if (run / name).exists():
            out[name.removesuffix(".json")] = json.loads((run / name).read_text() or "{}")
    for name in ("residue-processes.txt", "residue-sockets.txt"):
        if (run / name).exists():
            out[name.removesuffix(".txt")] = [line for line in (run / name).read_text().splitlines() if line]
    stim = _jsonl(run / "stimulus.jsonl")
    out["stimulusOutcome"] = stim[-1].get("outcome") if stim else None
    out["observer"] = observer_metrics(run)
    out["runtime"] = runtime_metrics(run)
    if out["kind"] == "lite":  # DLG-13: success requires every owned completion marker
        markers = set(out["maestro"].get("workArtifacts") or [])
        out["completion"] = {"ownedMarkers": sorted(markers), "allOwnedMarkers": markers == {"lite-driver-binding.marker",
                             "carla-adapter-binding.marker", "driver-stimulus-binding.marker"}}
        applied = [f for f in out["maestro"]["faultEvents"] if f["phase"] in ("apply", "clear")]
        th = out["runtime"].get("commandedThrottle")
        if len(applied) == 2 and th:  # review 1 R-13: where the freeze fell relative to the actuation
            a, c = applied[0]["hostS"], applied[1]["hostS"]
            out["faultTiming"] = {"appliedHostS": a, "clearedHostS": c, "throttleWindowHostS": [th["firstMonotonicNs"] / 1e9, th["lastMonotonicNs"] / 1e9],
                                  "overlapsThrottleWindow": a < th["lastMonotonicNs"] / 1e9 and c > th["firstMonotonicNs"] / 1e9}
    out["files"] = _hashes(run)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args()
    summaries = [run_summary(Path(r)) for r in args.runs]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(summaries, indent=2, sort_keys=True) + "\n")
    lines = ["# Lite CARLA closed-loop integration: run report", "",
             "Engineering integration evidence; not AEB validation, not a scientific result, not M1.", "",
             *("- " + n for n in NOTES), "",
             "| Run | Kind/case | Maestro verdict | Peak km/h (obs) | Onset->standstill s (obs) | Min accel m/s^2 (obs) | Distance m | Cleanup |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in summaries:
        m, o = s.get("maestro", {}), s["observer"]
        verdict = "n/a (legacy invocation)" if s["kind"] == "baseline" else f"{m.get('executionSucceeded')} {m.get('dispatchDiagnostic') or ''}{m.get('diagnostics') or ''}"
        if "restore-guard" in s:
            cleanup = f"guard restored={s['restore-guard'].get('restored')} destroyed={len(s['restore-guard'].get('destroyed', []))}"
        else:
            world = s.get("world-after", {})
            cleanup = f"world after: synchronous={world.get('synchronousMode')} vehicles={len(world.get('vehicles', []))}"
        lines.append(f"| {s['run']} | {s['kind']}/{m.get('case', '-')} | {verdict} | {o.get('peakKmh')} | {o.get('standstillAfterOnsetS')} | "
                     f"{o.get('minAccelForwardMps2')} | {o.get('distanceM')} | residue={len(s.get('residue-processes', []))}; {cleanup} |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
