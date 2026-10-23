"""Per-run audit of the S1d soak criteria (thesis 029 plan.md, Soak; DR-2 and DR-6 applied).

    python3 audit.py <run-dir> [<run-dir> ...]      -> one JSON verdict per run on stdout

Reads recorded evidence only; never touches CARLA, Maestro or the run. Each criterion is a list of named checks;
a run passes when every applicable check is true. A missing input is a failed check, never a pass (P8: "a
missing sample or footer is a failure, not INVALID"). P2 is reported as an observation, never a criterion.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import report  # noqa: E402  (the blueprint's report helpers: observer and runtime metrics)

WRITER_STATE = "ARGUS2-REASON-WRITER-STATE"
OWNED_ROLES = {"xverse-lite-ego", "xverse-lite-camera", "xverse-lite-radar"}


def _json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _jsonl(path: Path) -> list:
    try:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    except (OSError, ValueError):
        return []


def argus_roots(run: Path) -> dict:
    """``argus-verify.txt``: {'maestro': verdict, 'flows': verdict} (None when absent or unreadable)."""
    roots, current = {}, None
    try:
        lines = (run / "argus-verify.txt").read_text().splitlines()
    except OSError:
        return {"maestro": None, "flows": None}
    for line in lines:
        if line.startswith("== "):
            current = "maestro" if line.rstrip().endswith("argus-maestro") else "flows" if "argus-flows" in line else None
        elif current and line.startswith("{"):
            try:
                roots[current] = json.loads(line)
            except ValueError:
                roots[current] = None
    return {"maestro": roots.get("maestro"), "flows": roots.get("flows")}


def _closed_complete(verdict) -> bool:
    return bool(verdict) and verdict.get("writerState") == "closed" and verdict.get("evidenceStatus") == "complete" \
        and not verdict.get("evidenceReasons")


def _failed_writer_only(verdict, *, allow_closed: bool) -> bool:
    """DR-6 (b): a failed writer whose only reason is WRITER-STATE; a closed one (DR-2, P3 only) with none."""
    if not verdict:
        return False
    reasons = set(verdict.get("evidenceReasons") or [])
    if verdict.get("writerState") == "failed":
        return reasons <= {WRITER_STATE}
    return allow_closed and verdict.get("writerState") == "closed" and not reasons


def _residue(run: Path) -> bool:
    for name in ("residue-processes.txt", "residue-sockets.txt"):
        try:
            if (run / name).read_text().strip():
                return False
        except OSError:
            return False
    return True


def _world_restored(guard) -> bool:
    return bool(guard) and guard.get("restored") is True and guard.get("remaining") == [] and \
        (guard.get("after") or {}).get("synchronousMode") is False


def _native_attested(record) -> bool:
    units = record.get("nativeUnits") or []
    return len(units) == 4 and all(u.get("issued") and u.get("native_retired") and u.get("direct_child_reaped") for u in units)


def _unit_name(unit_id) -> str:
    return str(unit_id).rsplit("/", 1)[-1].removesuffix("-instance")


def preflight_ok(run: Path) -> dict:
    """P7: the single-owner preflight was never violated (no BLOCKED preflight, no competing client)."""
    try:
        log = (run / "run-live.log").read_text()
    except OSError:
        try:
            log = (run / "run-baseline.log").read_text()
        except OSError:
            return {"logPresent": False}
    try:
        competing = (run / "host-competing-processes.txt").read_text().strip()
    except OSError:
        competing = None
    return {"logPresent": True, "noBlocked": "BLOCKED" not in log, "noCompetingProcesses": competing == ""}


def actuator_safe_stop(run: Path, guard) -> dict:
    """P8 per path (FR-021, FR-022); the path is classified from the guard record."""
    rows = _jsonl(run / "observer.jsonl")
    footer = next((r for r in rows if r.get("footer")), None)
    samples = [r for r in rows if "frame" in r and not r.get("header") and not r.get("footer")]
    out = {"observerFooterSigterm": bool(footer) and footer.get("stoppedBy") == "SIGTERM", "samples": len(samples)}
    held = (guard or {}).get("held") or []
    if not guard:
        out["path"] = None
        out["guardRecord"] = False
        return out
    if not held:  # adapter-close path: the adapter held and destroyed the ego while the world stayed paused
        out["path"] = "adapter-close"
        ticks = [r for r in _jsonl(run / "driver" / "driver-ticks.jsonl") if r.get("kind") == "tick" and "frame" in r]
        last = ticks[-1]["frame"] if ticks else None
        frames = {r["frame"] for r in samples}
        ego_frames = [r["frame"] for r in samples if r.get("ego")]
        out.update(lastControlFrame=last, lastEgoFrame=max(ego_frames) if ego_frames else None,
                   noEgoAfterLastControl=last is not None and all(f <= last for f in ego_frames),
                   samplesAtLastAndNext=last is not None and last in frames and (last + 1) in frames)
        moving = [r for r in samples if r.get("ego")]
        out["lastEgoSpeedMps"] = moving[-1]["ego"]["speedMps"] if moving else None
    else:  # guard path: un-pause .. destroy, the ego never driven and reaching standstill before the destroy
        out["path"] = "guard"
        # windowed by frame (S1c finding 34, H1): from the first frame received after the un-pause to the last frame
        # that still shows the ego; the observer receives that last frame just after the guard's destroy time
        unpause, destroy = guard.get("unpauseMonotonicNs"), guard.get("destroyMonotonicNs")
        after = [r for r in samples if unpause and r["monotonicNs"] >= unpause]
        first = after[0]["frame"] if after else None
        ego_frames = [r["frame"] for r in after if r.get("ego")]
        last = max(ego_frames) if ego_frames else None
        window = [r for r in samples if r.get("ego") and first is not None and last is not None and destroy
                  and first <= r["frame"] <= last]
        before = [r for r in samples if r.get("ego") and first is not None and r["frame"] < first]
        # the last ego frame must be received within one frame period (+ slack) of the guard's destroy (finding 36)
        bounded = bool(window) and destroy is not None and window[-1]["monotonicNs"] <= destroy + 100_000_000
        base = before[-1]["ego"]["speedMps"] if before else (window[0]["ego"]["speedMps"] if window else None)
        out.update(windowSamples=len(window), unpauseSpeedMps=base,
                   neverDriven=bool(window) and base is not None and all(r["ego"]["speedMps"] <= base + 0.1 for r in window),
                   standstillBeforeDestroy=bounded and window[-1]["ego"]["speedMps"] < 0.05)
    return out


def _persistence_ok(timing) -> bool:
    """FR-002 metric: p99 <= 0.1 s, max <= 0.25 s, last-decile increase <= 0.05 s (recorded by the harness)."""
    if not timing or not timing.get("count"):
        return False
    return timing.get("p99S", 1) <= 0.1 and timing.get("maxS", 1) <= 0.25 and timing.get("lastDecileIncreaseS", 1) <= 0.05


def audit(run: Path) -> dict:
    run = Path(run)
    if (run / "baseline-status.txt").exists() or (run / "run-baseline.log").exists():
        status = (run / "baseline-status.txt").read_text().strip() if (run / "baseline-status.txt").exists() else ""
        exit_text = (run / "baseline-exit.txt").read_text().strip() if (run / "baseline-exit.txt").exists() else None
        p5 = {"exitZero": exit_text == "0",
              "cleanStatus": status == "status: stimulus_ok=1 virtual_vehicle=0 vcu=0 observer=0 vehicles_left=0 residue=0"}
        checks = {"P5": p5, "P7": preflight_ok(run)}
        return _verdict(run, "baseline", checks, {})
    record = _json(run / "maestro-run.json") or {}
    case = record.get("case")
    guard = _json(run / "restore-guard.json")
    roots = argus_roots(run)
    checks, observations = {}, {}
    if case in ("nominal", "freeze-vcu", "long-run"):
        checks["P1"] = {"succeededWithMarkers": record.get("executionSucceeded") is True and record.get("markersOk") is True,
                        "maestroRootClosedComplete": _closed_complete(roots["maestro"]),
                        "flowRootClosedComplete": _closed_complete(roots["flows"]),
                        "noResidue": _residue(run), "worldRestoredNoVehicles": _world_restored(guard)}
        observations["P2"] = {"observer": report.observer_metrics(run), "runtime": report.runtime_metrics(run)}
        # S1b stop modes (exited-on-term or forced) per unit, from the native closure facts: an observation here; the
        # harness asserts exited-on-term for the owned units, so a violation fails the run through its exit (S1c finding 40)
        observations["P1"] = {"stopModes": {_unit_name(u.get("unit_id")): u.get("stop_mode") for u in record.get("nativeUnits") or []
                                            if isinstance(u, dict)} or None}
    if case == "cancel-paused":
        checks["P3"] = {"cancelled": record.get("dispatchDiagnostic") == "ML-SCHEDULE-CANCELLED",
                        "cancelIssuedDuringRun": "cancelReturnedMonotonicNs" in record and "cancelNotIssued" not in record,
                        "maestroWriterDr6": _failed_writer_only(roots["maestro"], allow_closed=True),
                        "noPersistenceFailure": record.get("persistenceFailure") is None,
                        "cleanupComplete": record.get("cleanupComplete") is True,
                        "nativeAttested": _native_attested(record),
                        "guardDestroyedOwned": bool(guard) and {d.get("roleName") for d in guard.get("destroyed") or []} >= OWNED_ROLES
                        and guard.get("remaining") == [],
                        "noResidue": _residue(run)}
        observations["flowRoot"] = roots["flows"]  # DR-6 (c): reported, not a criterion until S1b's graceful stop
        observations["brokerCancel"] = record.get("brokerCancelResult")
    if case == "no-carla":
        # DR-14: a readiness-declaring adapter fails readiness before its own connection timeout ends it
        checks["P4"] = {"childExit": record.get("dispatchDiagnostic") in ("ML-RUN-CHILD-EXIT", "ML-PROBE-NOT-READY"),
                        "cleanupComplete": record.get("cleanupComplete") is True,
                        "maestroWriterFailedDr6": _failed_writer_only(roots["maestro"], allow_closed=False),
                        "noResidue": _residue(run)}
        observations["flowRoot"] = roots["flows"]
    if case == "long-run":
        failure = record.get("persistenceFailure") or {}
        diagnostics = set(record.get("diagnostics") or []) | {record.get("dispatchDiagnostic")} | \
            set(record.get("closureDiagnostics") or []) | {failure.get("diagnostic")}  # S1c finding 34, H2
        after = None
        tick = record.get("tickTiming") or {}
        if record.get("startReturnedMonotonicNs") and tick.get("lastTickS") is not None:
            after = (record["startReturnedMonotonicNs"] - record["monotonicStartNs"]) / 1e9 - tick["lastTickS"]
        # P6 "the live closure stays within 2 s" is the terminal budget of each closure call (FR-002; run_closure.py
        # terminal <= 2 s): every terminal-report, closure and abort persistence call (S1c finding 31)
        timing = record.get("persistenceTiming") or {}
        closure_calls = [s for kind, s in timing.get("terminalCallsS") or [] if kind in ("terminal-report", "closure", "abort")]
        # a terminal call is cut off at its own deadline (<= 2 s): a timed-out call is caught by the recorded persistence
        # failure (S1c finding 34, H2); the duration check is the plan's "within 2 s" (finding 36)
        checks["P6"] = {"noPersistTimeout": "ML-PERSIST-TIMEOUT" not in diagnostics,
                        "noServiceDeadline": "ML-SCHEDULE-SERVICE-DEADLINE" not in diagnostics,
                        "noPersistenceFailure": not failure,
                        "persistenceRoundTrip": _persistence_ok(timing),
                        "closureCallsWithin2s": bool(closure_calls) and max(closure_calls) <= 2.0}
        observations["P6"] = {"closureCallsMaxS": max(closure_calls) if closure_calls else None,
                              "afterLastTickS": round(after, 3) if after is not None else None,
                              "persistenceTiming": timing, "tickTiming": tick}
    if case is None:
        checks["record"] = {"maestroRunJson": False}
    checks["P7"] = preflight_ok(run)
    if case in ("nominal", "freeze-vcu", "long-run", "cancel-paused"):
        p8 = actuator_safe_stop(run, guard)
        path_ok = (p8.get("noEgoAfterLastControl") and p8.get("samplesAtLastAndNext")) if p8.get("path") == "adapter-close" else \
            (p8.get("neverDriven") and p8.get("standstillBeforeDestroy")) if p8.get("path") == "guard" else False
        checks["P8"] = {"observerFooterSigterm": p8["observerFooterSigterm"], "pathHolds": bool(path_ok)}
        observations["P8"] = p8
    return _verdict(run, case, checks, observations)


def _verdict(run, case, checks, observations):
    failed = sorted(f"{criterion}.{name}" for criterion, items in checks.items() for name, ok in items.items()
                    if isinstance(ok, bool) and not ok)
    return {"run": run.name, "case": case, "pass": not failed, "failedChecks": failed, "checks": checks,
            "observations": observations}


def main(argv=None) -> int:
    verdicts = [audit(Path(a)) for a in (argv or sys.argv[1:])]
    for v in verdicts:
        print(json.dumps(v, sort_keys=True, default=str))
    return 0 if all(v["pass"] for v in verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
