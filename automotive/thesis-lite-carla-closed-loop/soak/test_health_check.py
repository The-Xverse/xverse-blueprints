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
        def __init__(self, host, port):
            pass

        def set_timeout(self, seconds):
            pass

        def get_world(self):
            return world

    monkeypatch.setitem(sys.modules, "carla", types.SimpleNamespace(Client=Client))
    code = health_check.main(["--carla-site", str(tmp_path)])
    return code, json.loads(capsys.readouterr().out)


def test_a_fresh_synchronous_server_is_healthy_without_a_tick(monkeypatch, tmp_path, capsys):
    world = FakeWorld(synchronous=True, tick_ok=False)  # no tick owner: wait_for_tick would time out
    code, result = _run(monkeypatch, tmp_path, capsys, world)
    assert code == 0 and result["healthy"] and result["tickProbe"] == "skipped-synchronous" and result["frame"] == 41
    assert result["synchronousMode"] is True and world.waited == 0 and world.ticked == 0


def test_an_asynchronous_server_must_produce_a_frame(monkeypatch, tmp_path, capsys):
    code, result = _run(monkeypatch, tmp_path, capsys, FakeWorld(synchronous=False))
    assert code == 0 and result["healthy"] and result["tickProbe"] == "wait-for-tick" and result["frame"] == 42


def test_an_asynchronous_server_without_frames_is_unhealthy(monkeypatch, tmp_path, capsys):
    code, result = _run(monkeypatch, tmp_path, capsys, FakeWorld(synchronous=False, tick_ok=False))
    assert code == 1 and not result["healthy"] and "time-out" in result["error"]


def test_an_unanswering_server_is_unhealthy(monkeypatch, tmp_path, capsys):
    world = FakeWorld(synchronous=True)
    world.get_snapshot = lambda: (_ for _ in ()).throw(RuntimeError("time-out while waiting for the simulator"))
    code, result = _run(monkeypatch, tmp_path, capsys, world)
    assert code == 1 and not result["healthy"]
