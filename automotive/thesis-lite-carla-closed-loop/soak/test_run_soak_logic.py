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
        self.runs, self.starts, self.stops = [], 0, 0

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
    def make(statuses, start_health=None):
        fake = Fake(statuses, start_health)
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
