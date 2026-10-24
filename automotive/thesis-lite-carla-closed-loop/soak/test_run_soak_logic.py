"""Offline checks of the soak runner's control flow (S1c finding 34): no CARLA, no Maestro.

    python3 -B -m pytest -q soak/test_run_soak_logic.py   (from the blueprint directory)

Server start/stop and single runs are replaced by fakes; the schedule, INVALID and restart handling, the server-
failure limit, observation repeats and the FR-020 stop are exercised on the real Soak class.
"""

import json
from pathlib import Path

import pytest

import run_soak


class Fake:
    def __init__(self, statuses, start_health=None):
        self.statuses, self.start_health = list(statuses), list(start_health or [])
        self.runs, self.starts, self.stops, self.warm_ups = [], 0, 0, []

    def run_one(self, soak, case, carla):
        status = self.statuses.pop(0) if self.statuses else "PASS"
        entry = {"case": case, "run": f"r{len(self.runs)}", "status": status, "server": soak.server_index if carla else None,
                 "loadMax": 1.0}
        soak.runs.append(entry)
        self.runs.append((case, status))
        return entry

    def start(self, out, home):
        self.starts += 1
        return {"healthy": self.start_health.pop(0) if self.start_health else True}

    def stop(self, out):
        self.stops += 1


@pytest.fixture
def soak(tmp_path, monkeypatch):
    def make(statuses, start_health=None, warm_up=False):
        fake = Fake(statuses, start_health)
        if not warm_up:  # the warm-up (DR-18) has its own tests below; here it neither runs nor consumes a status
            monkeypatch.setattr(run_soak.Soak, "_warm_up", lambda self: fake.warm_ups.append(self.server_index) or True)
        monkeypatch.setattr(run_soak, "identities", lambda c, b: {"compat": {"clean": True, "detached": True},
                                                                  "blueprints": {"clean": True, "detached": True},
                                                                  "runnerMatchesPinned": True})
        monkeypatch.setattr(run_soak, "start_server", fake.start)
        monkeypatch.setattr(run_soak, "stop_server", fake.stop)
        monkeypatch.setattr(run_soak, "carla_pids", lambda: [])
        monkeypatch.setattr(run_soak, "port_listening", lambda port: False)
        monkeypatch.setattr(run_soak, "load1", lambda: 1.0)
        monkeypatch.setattr(run_soak.Soak, "run_one", lambda self, case, carla: fake.run_one(self, case, carla))
        return run_soak.Soak(tmp_path / "c", tmp_path / "b", tmp_path / "out"), fake
    return make


def test_clean_soak_runs_the_predeclared_counts(soak):
    s, fake = soak([])
    assert s.execute() == 0
    counts = {}
    for case, _ in fake.runs:
        counts[case] = counts.get(case, 0) + 1
    assert counts == {"no-carla": 10, "nominal": 30, "freeze-vcu": 30, "cancel-paused": 30, "long-run": 30, "baseline": 10}
    report = json.loads((s.out / "soak-report.json").read_text())
    assert report["valid"] and report["cases"]["nominal"]["upperBound95"] == 0.095


def test_first_failure_stops_the_soak(soak):
    s, fake = soak(["PASS"] * 5 + ["FAIL"])
    assert s.execute() == 2
    assert len(fake.runs) == 6 and json.loads(s.manifest.read_text())["state"] == "stopped"


def test_invalid_restarts_counts_and_repeats_at_block_end(soak):
    s, fake = soak(["PASS"] * 3 + ["INVALID"])  # the 4th run (first CARLA run after the 3 gap no-carla runs) is INVALID
    assert s.execute() == 0
    assert s.server_failures == 1 and fake.starts == 3 + 1  # three block starts and one restart
    repeats = [e for e in s.runs if e.get("repeatOf") == "INVALID"]
    assert len(repeats) == 1 and repeats[0]["case"] == "nominal"


def test_more_than_three_server_failures_stop_the_soak(soak):
    s, fake = soak(["PASS"] * 3 + ["INVALID"] * 4)
    assert s.execute() == 2
    assert "server failures" in json.loads(s.manifest.read_text())["stopReason"]


def test_a_failed_restart_counts_as_a_server_failure(soak):
    s, fake = soak(["PASS"] * 3 + ["INVALID"], start_health=[True, False, True])  # block start ok, restart fails, retry ok
    assert s.execute() == 0
    assert s.server_failures == 2
    events = [r["serverEvent"] for r in s.runs if "serverEvent" in r]
    assert "restart failed health" in events


def test_two_failed_starts_in_a_row_stop_the_soak(soak):
    s, fake = soak([], start_health=[False, False])  # the first block's start and its restart both fail (DR-11)
    assert s.execute() == 2
    assert "twice in a row" in json.loads(s.manifest.read_text())["stopReason"]
    assert s.server_failures == 2


def test_a_failure_in_an_invalid_repeat_stops_the_soak(soak):
    # first CARLA run INVALID; the repeat at the end of block 1 (after 10 rounds = 41 runs) FAILs
    statuses = ["PASS"] * 3 + ["INVALID"] + ["PASS"] * 42 + ["FAIL"]
    s, fake = soak(statuses)
    assert s.execute() == 2
    assert [e for e in s.runs if e.get("repeatOf") == "INVALID"][0]["status"] == "FAIL"


def test_no_carla_only_observation_repeats_do_not_crash(soak, monkeypatch):
    statuses = ["OBSERVATION"] + ["PASS"] * 200
    s, fake = soak(statuses)
    monkeypatch.setattr(run_soak, "stop_server", REAL_STOP)  # the real one: it must create the empty slot directory
    assert s.execute() == 0
    assert [e for e in s.runs if e.get("repeatOf") == "OBSERVATION"][0]["case"] == "no-carla"
    assert (s.out / "soak-report.json").exists()


REAL_STOP = run_soak.stop_server


@pytest.mark.parametrize("kw, status", [
    (dict(carla=True, healthy_before=True, after={"healthy": False, "synchronousMode": True}, audit_pass=True, script_exit=0, load_max=1), "FAIL"),
    # DR-21: a synchronous world after the cleanup is a restore failure even when the server answers
    (dict(carla=True, healthy_before=True, after={"healthy": True, "synchronousMode": True}, audit_pass=True, script_exit=0, load_max=1), "FAIL"),
    (dict(carla=True, healthy_before=True, after={"healthy": True, "synchronousMode": False}, audit_pass=True, script_exit=0, load_max=1), "PASS"),
    (dict(carla=True, healthy_before=True, after={"healthy": False}, audit_pass=True, script_exit=0, load_max=1), "INVALID"),
    (dict(carla=True, healthy_before=False, after={"healthy": True}, audit_pass=False, script_exit=1, load_max=1), "INVALID"),
    (dict(carla=True, healthy_before=True, after={"healthy": True}, audit_pass=True, script_exit=1, load_max=1), "FAIL"),
    (dict(carla=True, healthy_before=True, after={"healthy": True}, audit_pass=False, script_exit=0, load_max=1), "FAIL"),
    (dict(carla=True, healthy_before=True, after={"healthy": True}, audit_pass=True, script_exit=0, load_max=11), "OBSERVATION"),
    (dict(carla=False, healthy_before=False, after=None, audit_pass=True, script_exit=0, load_max=1), "PASS"),
])
def test_classify(kw, status):  # DR-12 (S1c findings 34-36)
    assert run_soak.classify(**kw) == status


def test_invalid_then_two_failed_restarts_names_dr11(soak):
    s, fake = soak(["PASS"] * 3 + ["INVALID"], start_health=[True, False, False])
    assert s.execute() == 2
    assert "twice in a row" in json.loads(s.manifest.read_text())["stopReason"]


def test_runner_differing_from_the_pinned_copy_is_refused(soak, monkeypatch):
    s, fake = soak([])
    s.pinned["runnerMatchesPinned"] = False
    assert s.execute() == 4 and not fake.runs


def test_any_exit_stops_a_running_server(soak, monkeypatch):
    s, fake = soak(["PASS"] * 3)
    state = {"pids": []}
    monkeypatch.setattr(run_soak, "carla_pids", lambda: state["pids"])

    def boom(self, case, carla):
        state["pids"] = [12345]  # a server is up when the crash happens
        raise RuntimeError("crash")
    monkeypatch.setattr(run_soak.Soak, "run_one", boom)
    with pytest.raises(RuntimeError):
        s.execute()
    assert fake.stops >= 1


def test_the_child_run_keeps_the_pinned_platform_export_and_driver_venv(tmp_path, monkeypatch):
    """S1c finding 40: development overrides never reach a soak run (run-live.sh then uses its pinned defaults)."""
    from types import SimpleNamespace

    monkeypatch.setenv("XVERSE_PLATFORM_SRC", "/nonexistent/platform-src")
    monkeypatch.setenv("XVERSE_LIVE_DRIVER_VENV", "/nonexistent/driver-venv")
    monkeypatch.setattr(run_soak, "identities", lambda c, b: {"compat": {"clean": True, "detached": True},
                                                              "blueprints": {"clean": True, "detached": True},
                                                              "runnerMatchesPinned": True})
    monkeypatch.setattr(run_soak, "load1", lambda: 1.0)
    seen = []

    def run(command, env=None, **kwargs):
        seen.append((command, env))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run_soak.subprocess, "run", run)
    (tmp_path / "out").mkdir()
    s = run_soak.Soak(tmp_path / "c", tmp_path / "b", tmp_path / "out")
    entry = s.run_one("no-carla", carla=False)
    (command, env), = seen
    assert command[0] == "timeout" and command[2].endswith("run-live.sh") and entry["status"] == "FAIL"  # no run directory
    assert "XVERSE_PLATFORM_SRC" not in env and "XVERSE_LIVE_DRIVER_VENV" not in env and env["XVERSE_COMPAT_SRC"] == str(tmp_path / "c")


def test_every_server_start_gets_one_warm_up_excluded_from_the_statistics(soak):
    """DR-18 (S1c finding 47): one warm-up nominal run after each healthy start, reported apart."""
    s, fake = soak([], warm_up=True)
    assert s.execute() == 0
    warm = [e for e in s.runs if e.get("warmUp")]
    assert len(warm) == fake.starts == 3 and all(e["case"] == "warm-up" and e["warmUpCase"] == "nominal" for e in warm)
    assert [c for c, _ in fake.runs].count("nominal") == 30 + 3  # the harness ran nominal for each warm-up
    report = json.loads((s.out / "soak-report.json").read_text())
    assert report["cases"]["nominal"]["runs"] == 30 and "warm-up" not in report["cases"]
    assert [w["status"] for w in report["warmUps"]] == ["PASS"] * 3 and report["valid"]


def test_a_clean_readiness_failure_in_a_warm_up_is_excused(soak, monkeypatch):
    s, fake = soak(["PASS"] * 3 + ["FAIL"], warm_up=True)  # three gap no-carla runs, then the first warm-up FAILs
    monkeypatch.setattr(run_soak, "clean_readiness_failure", lambda entry, run_dir: True)
    assert s.execute() == 0
    report = json.loads((s.out / "soak-report.json").read_text())
    assert report["warmUps"][0]["status"] == "FAIL" and report["warmUps"][0]["warmUpExcused"] and report["valid"]
    assert report["cases"]["nominal"]["failures"] == 0


def test_any_other_warm_up_failure_stops_the_soak(soak, monkeypatch):
    """DR-19 (2): for example a restore failure or a residue in the warm-up is a criterion failure (finding 50 MEDIUM-1)."""
    s, fake = soak(["PASS"] * 3 + ["FAIL"], warm_up=True)
    monkeypatch.setattr(run_soak, "clean_readiness_failure", lambda entry, run_dir: False)
    assert s.execute() == 2
    manifest = json.loads(s.manifest.read_text())
    assert manifest["state"] == "stopped" and "warm-up" in manifest["stopReason"]
    assert len(fake.runs) == 4  # nothing ran after the failed warm-up


def _write_run(tmp_path, diagnostic="ML-PROBE-NOT-READY", cleanup=True, residue="", path="adapter-close", control=None):
    run_dir = tmp_path / "w"
    run_dir.mkdir()
    (run_dir / "maestro-run.json").write_text(json.dumps({"dispatchDiagnostic": diagnostic, "cleanupComplete": cleanup}))
    (run_dir / "residue-processes.txt").write_text(residue)
    (run_dir / "soak-audit.json").write_text(json.dumps({"observations": {"P8": {"path": path, "lastControlFrame": control}}}))
    return run_dir


@pytest.mark.parametrize("change, excused", [
    ({}, True),
    ({"diagnostic": "ML-SCHEDULE-COLLECTION-INCOMPLETE"}, False),
    ({"cleanup": False}, False),
    ({"residue": "123 python3 -m xverse_compat.live.driver"}, False),
    ({"healthy": False}, False),
    ({"checks": ["P1.succeededWithMarkers", "P3.guardDestroyedOwned"]}, False),
    ({"path": "guard"}, False),  # finding 53 LOW-1: P8 is excused only on the adapter-close path
    ({"control": 12}, False),  # ... and only when no control was ever sent
])
def test_clean_readiness_failure(tmp_path, change, excused):
    run_dir = _write_run(tmp_path, **{k: v for k, v in change.items() if k in ("diagnostic", "cleanup", "residue", "path", "control")})
    entry = {"healthAfter": {"healthy": change.get("healthy", True)},
             "audit": {"failedChecks": change.get("checks", ["P1.succeededWithMarkers", "P8.pathHolds"])}}
    assert run_soak.clean_readiness_failure(entry, run_dir) is excused
    assert run_soak.clean_readiness_failure(entry, tmp_path / "missing") is False


def test_a_warm_up_that_leaves_the_server_unhealthy_is_a_failed_start(soak):
    s, fake = soak(["PASS"] * 3 + ["INVALID"], warm_up=True)
    assert s.execute() == 0
    events = [r["serverEvent"] for r in s.runs if "serverEvent" in r]
    assert "warm-up left the server unhealthy" in events and "start failed health" in events
    assert s.server_failures == 1 and fake.starts == 3 + 1
    assert len([e for e in s.runs if e.get("warmUp")]) == 4  # the restarted server gets its own warm-up


def test_an_operator_signal_stops_the_soak_between_runs(soak, monkeypatch):
    """S1c finding 60: SIGTERM only sets a flag; the run in progress completes, the soak stops before the next one,
    and the finally-block stops a running server."""
    import os
    import signal

    s, fake = soak([])
    original = fake.run_one
    servers = {"running": False}

    def run_one(soak_, case, carla):
        entry = original(soak_, case, carla)
        if len(fake.runs) == 2:
            servers["running"] = True  # stands in for a server left up at the moment of the signal
            os.kill(os.getpid(), signal.SIGTERM)
        return entry

    monkeypatch.setattr(run_soak.Soak, "run_one", lambda self, case, carla: run_one(self, case, carla))
    monkeypatch.setattr(run_soak, "carla_pids", lambda: [1] if servers["running"] else [])
    stops = []
    monkeypatch.setattr(run_soak, "stop_server", lambda out: (stops.append(out), servers.update(running=False)))
    assert s.execute() == 2
    manifest = json.loads(s.manifest.read_text())
    assert manifest["state"] == "stopped" and "operator signal SIGTERM" in manifest["stopReason"]
    assert len(fake.runs) == 2 and stops  # no run after the signal; the server was stopped
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL or callable(signal.getsignal(signal.SIGTERM))
