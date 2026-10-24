"""Offline checks of health_check.py with a fake ``carla`` module (S1c finding 57, thesis DR-21): no CARLA."""

import json
import sys
import types

import pytest

import health_check


class FakeWorld:
    def __init__(self, synchronous, tick_ok=True):
        self.synchronous, self.tick_ok, self.ticked, self.waited = synchronous, tick_ok, 0, 0

    def get_settings(self):
        return types.SimpleNamespace(synchronous_mode=self.synchronous, fixed_delta_seconds=0.05 if self.synchronous else None)

    def get_map(self):
        return types.SimpleNamespace(name="Carla/Maps/Town10HD_Opt")

    def get_actors(self):
        return types.SimpleNamespace(filter=lambda pattern: [])

    def get_snapshot(self):
        return types.SimpleNamespace(frame=41)

    def wait_for_tick(self, seconds):
        self.waited += 1
        if not self.tick_ok:
            raise RuntimeError("time-out of 5000ms while waiting for the simulator")
        return types.SimpleNamespace(frame=42)

    def tick(self, *args):  # the check must never call this
        self.ticked += 1
        raise AssertionError("the health check ticked the world")


def _run(monkeypatch, tmp_path, capsys, world):
    class Client:
        timeouts = []

        def __init__(self, host, port):
            pass

        def set_timeout(self, seconds):
            Client.timeouts.append(seconds)

        def get_world(self):
            return world

    monkeypatch.setitem(sys.modules, "carla", types.SimpleNamespace(Client=Client))
    code = health_check.main(["--carla-site", str(tmp_path)])
    result = json.loads(capsys.readouterr().out)
    assert Client.timeouts == [15.0]  # every server request runs under the 15 s client timeout (finding 58, LOW-5)
    return code, result


def test_a_fresh_synchronous_server_is_healthy_without_a_tick(monkeypatch, tmp_path, capsys):
    world = FakeWorld(synchronous=True, tick_ok=False)  # no tick owner: wait_for_tick would time out
    code, result = _run(monkeypatch, tmp_path, capsys, world)
    assert code == 0 and result["healthy"] and result["tickProbe"] == "skipped-synchronous"
    assert result["localSnapshotFrame"] == 41 and "frame" not in result and "waitForTickS" not in result  # LOW-6
    assert result["synchronousMode"] is True and world.waited == 0 and world.ticked == 0


def test_an_asynchronous_server_must_produce_a_frame(monkeypatch, tmp_path, capsys):
    code, result = _run(monkeypatch, tmp_path, capsys, FakeWorld(synchronous=False))
    assert code == 0 and result["healthy"] and result["tickProbe"] == "wait-for-tick" and result["frame"] == 42


def test_an_asynchronous_server_without_frames_is_unhealthy(monkeypatch, tmp_path, capsys):
    code, result = _run(monkeypatch, tmp_path, capsys, FakeWorld(synchronous=False, tick_ok=False))
    assert code == 1 and not result["healthy"] and "time-out" in result["error"]


@pytest.mark.parametrize("request_name", ["get_settings", "get_map"])
@pytest.mark.parametrize("synchronous", [True, False])
def test_a_server_that_does_not_answer_a_request_is_unhealthy(monkeypatch, tmp_path, capsys, request_name, synchronous):
    """The server requests are the evidence (finding 58, MEDIUM-1 and LOW-5): a time-out at either is unhealthy."""
    world = FakeWorld(synchronous=synchronous)

    def timed_out():
        raise RuntimeError("time-out of 15000ms while waiting for the simulator")

    setattr(world, request_name, timed_out)
    code, result = _run(monkeypatch, tmp_path, capsys, world)
    assert code == 1 and not result["healthy"] and "time-out" in result["error"]
