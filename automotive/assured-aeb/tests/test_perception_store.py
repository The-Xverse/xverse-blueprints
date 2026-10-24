"""Offline tests of the WP-09 frame store on a temporary directory (never the loop10 dataset root).
The floor and the frame length below are test values."""

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
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096)
    raw, sha = frame()
    record = store.put(raw, sha)
    assert record["status"] == "stored" and record["rawBytes"] == 4096 and set(record) == {"rawSha256", "rawBytes", "storedBytes", "status"}
    assert (tmp_path / sha[:2] / f"{sha}.zlib").is_file()
    assert store.get(sha) == raw
    assert store.put(raw, sha)["status"] == "present"  # idempotent
    assert not any(p.name.startswith(".tmp-") for p in tmp_path.rglob("*"))


def test_digest_and_length_are_verified(tmp_path):
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096)
    raw, sha = frame()
    with pytest.raises(S.FrameStoreError, match="do not match"):
        store.put(raw[:-1] + b"\x00", sha)
    short, short_sha = frame(size=100)
    with pytest.raises(S.FrameStoreError, match="length"):
        store.put(short, short_sha)
    with pytest.raises(S.FrameStoreError):
        store.path("not-a-digest")


def test_corrupted_store_entry_fails_its_digest(tmp_path):
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=None)
    raw, sha = frame()
    store.put(raw, sha)
    import zlib
    store.path(sha).write_bytes(zlib.compress(b"tampered"))
    with pytest.raises(S.FrameStoreError, match="digest"):
        store.get(sha)


def test_free_space_floor_refuses(tmp_path):
    free = shutil.disk_usage(tmp_path).free
    store = S.FrameStore(tmp_path, free_space_floor_bytes=free + 1, compression_level=6, frame_length=None)
    raw, sha = frame()
    with pytest.raises(S.FrameStoreError, match="floor"):
        store.put(raw, sha)
    assert not store.path(sha).exists()


@pytest.mark.parametrize("kwargs", [{"free_space_floor_bytes": -1, "compression_level": 6, "frame_length": None},
                                    {"free_space_floor_bytes": 0, "compression_level": 10, "frame_length": None},
                                    {"free_space_floor_bytes": 0, "compression_level": 6, "frame_length": 0}])
def test_store_parameters_are_refused(tmp_path, kwargs):
    with pytest.raises(ValueError):
        S.FrameStore(tmp_path, **kwargs)
    with pytest.raises(ValueError):
        S.FrameStore("relative/root", free_space_floor_bytes=0, compression_level=6, frame_length=None)


def test_rename_is_followed_by_a_directory_fsync(tmp_path, monkeypatch):  # finding 4 / LOW-2
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096)
    synced = []
    monkeypatch.setattr(S, "_fsync_dir", lambda path: synced.append(path))
    raw, sha = frame(seed=7)
    store.put(raw, sha)
    assert synced == [tmp_path / sha[:2]]


def test_stale_temporary_files_are_swept_on_open(tmp_path):  # finding 4 / LOW-2
    raw, sha = frame(seed=8)
    S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096).put(raw, sha)
    shard = tmp_path / sha[:2]
    (shard / ".tmp-abc123.zlib").write_bytes(b"partial")
    (shard / ".tmp-keep.txt").write_bytes(b"not ours")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / ".tmp-x.zlib").write_bytes(b"outside a shard")
    store = S.FrameStore(tmp_path, free_space_floor_bytes=0, compression_level=6, frame_length=4096)
    assert store.swept == 1 and not (shard / ".tmp-abc123.zlib").exists()
    assert (shard / ".tmp-keep.txt").exists() and (tmp_path / "notes" / ".tmp-x.zlib").exists()
    assert store.get(sha) == raw
