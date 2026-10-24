"""Offline tests of the WP-09 frame store on a temporary directory (never the loop10 dataset root).
The floor, the compression level and the frame length below are test values."""

from __future__ import annotations

import hashlib
import os
import random
import shutil

import pytest

from assured_aeb.perception import store as S


def frame(seed=1, size=4096):
    data = random.Random(seed).randbytes(size)
    return data, hashlib.sha256(data).hexdigest()


def test_round_trip_and_layout(tmp_path):
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=True)
    raw, sha = frame()
    record = store.put(raw, sha)
    assert record["status"] == "stored" and record["rawBytes"] == 4096 and set(record) == {"rawSha256", "rawBytes", "storedBytes", "status"}
    assert (tmp_path / sha[:2] / f"{sha}.zlib").is_file()
    assert store.get(sha) == raw
    assert store.put(raw, sha)["status"] == "present"  # idempotent
    assert not any(p.name.startswith(".tmp-") for p in tmp_path.rglob("*"))


def test_digest_and_length_are_verified(tmp_path):
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=True)
    raw, sha = frame()
    with pytest.raises(S.FrameStoreError, match="do not match"):
        store.put(raw[:-1] + b"\x00", sha)
    short, short_sha = frame(size=100)
    with pytest.raises(S.FrameStoreError, match="length"):
        store.put(short, short_sha)
    with pytest.raises(S.FrameStoreError):
        store.path("not-a-digest")


def test_corrupted_store_entry_fails_its_digest(tmp_path):
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=None, writable=True)
    raw, sha = frame()
    store.put(raw, sha)
    import zlib
    store.path(sha).write_bytes(zlib.compress(b"tampered"))
    with pytest.raises(S.FrameStoreError, match="digest"):
        store.get(sha)


def test_free_space_floor_refuses(tmp_path):
    free = shutil.disk_usage(tmp_path).free
    store = S.FrameStore(tmp_path, free_space_floor_bytes=free + 1, compression_level=6, frame_length=None, writable=True)
    raw, sha = frame()
    with pytest.raises(S.FrameStoreError, match="floor"):
        store.put(raw, sha)
    assert not store.path(sha).exists()


@pytest.mark.parametrize("kwargs", [{"free_space_floor_bytes": -1, "compression_level": 6, "frame_length": None},
                                    {"free_space_floor_bytes": 0, "compression_level": 10, "frame_length": None},
                                    {"free_space_floor_bytes": 0, "compression_level": 6, "frame_length": 0}])
def test_store_parameters_are_refused(tmp_path, kwargs):
    with pytest.raises(ValueError):
        S.FrameStore(tmp_path, **kwargs, writable=True)
    with pytest.raises(ValueError):
        S.FrameStore("relative/root", free_space_floor_bytes=0, compression_level=6, frame_length=None, writable=True)


def test_rename_is_followed_by_a_directory_fsync(tmp_path, monkeypatch):  # finding 4 / LOW-2
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=True)
    synced = []
    monkeypatch.setattr(S, "_fsync_dir", lambda path: synced.append(path))
    raw, sha = frame(seed=7)
    store.put(raw, sha)
    assert synced == [tmp_path, tmp_path / sha[:2]]  # finding 7 / LOW-4: the root after a new shard, then the shard
    synced.clear()
    other = next((f for f in (frame(seed=k) for k in range(100, 5000)) if f[1][:2] == sha[:2]))
    store.put(*other)
    assert synced == [tmp_path / sha[:2]]  # an existing shard: no root fsync


def test_stale_temporary_files_are_swept_on_open(tmp_path):  # finding 4 / LOW-2
    raw, sha = frame(seed=8)
    S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=True).put(raw, sha)
    shard = tmp_path / sha[:2]
    (shard / ".tmp-abc123.zlib").write_bytes(b"partial")
    (shard / ".tmp-keep.txt").write_bytes(b"not ours")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / ".tmp-x.zlib").write_bytes(b"outside a shard")
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=True)
    assert store.swept == 1 and not (shard / ".tmp-abc123.zlib").exists()
    assert (shard / ".tmp-keep.txt").exists() and (tmp_path / "notes" / ".tmp-x.zlib").exists()
    assert store.get(sha) == raw


# ---- finding 7 / LOW-4: the sweep runs only on writable opens --------------------------------------------------

def test_read_only_open_does_not_sweep_and_refuses_put(tmp_path):
    raw, sha = frame(seed=9)
    S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=True).put(raw, sha)
    stale = tmp_path / sha[:2] / ".tmp-abc123.zlib"
    stale.write_bytes(b"partial")
    reader = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=False)
    assert reader.swept == 0 and stale.exists() and reader.get(sha) == raw
    with pytest.raises(S.FrameStoreError, match="read-only"):
        reader.put(*frame(seed=10))


@pytest.mark.parametrize("value", [None, 1, "yes"])
def test_writable_is_required_and_a_bool(tmp_path, value):
    with pytest.raises(TypeError):
        S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=None)
    with pytest.raises(ValueError, match="writable"):
        S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=None, writable=value)


@pytest.mark.parametrize("second_writable, survives", [(False, True), (True, False)])
def test_an_open_during_a_put(tmp_path, monkeypatch, second_writable, survives):
    """The finding 6 probe: a read-only open during ``put`` leaves the writer's temporary file; a second writable open
    (the declared single-writer limit) still removes it, and the writer fails loudly."""

    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=True)
    real_replace = os.replace

    def replace(source, target):
        S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096, writable=second_writable)
        return real_replace(source, target)

    monkeypatch.setattr(S.os, "replace", replace)
    raw, sha = frame(seed=11)
    if survives:
        assert store.put(raw, sha)["status"] == "stored" and store.get(sha) == raw
    else:
        with pytest.raises(FileNotFoundError):
            store.put(raw, sha)
        assert not store.path(sha).exists()
