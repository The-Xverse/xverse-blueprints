"""Offline-only strict JSON and bounded read-only files; no framework or output effects (training4a)."""
from __future__ import annotations

import hashlib
from contextlib import ExitStack
import json
import math
import os
from pathlib import Path
import stat
import sys
import zlib


def require(condition, message):
    if not condition:
        raise ValueError(message)


def exact(record, members, name):
    require(type(record) is dict and set(record) == set(members), f"{name}: exact members {sorted(members)} required")
    return record


def integer(value, name, low=0, high=None):
    require(type(value) is int and value >= low and (high is None or value <= high), f"{name}: integer out of range")
    return value


def number(value, name, low=None, high=None, *, positive=False):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    require(finite and (low is None or value >= low) and (high is None or value <= high)
            and (not positive or value > 0), f"{name}: finite representable number out of range")
    return value


def text(value, name):
    require(type(value) is str and bool(value) and "\x00" not in value, f"{name}: nonempty text required")
    return value


def digest(value, name):
    require(type(value) is str and len(value) == 64 and set(value) <= set("0123456789abcdef"), f"{name}: bare SHA256 required")
    return value


def canonical(record):
    try:
        return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError("record is not canonical JSON") from error


def sha(data):
    return hashlib.sha256(data).hexdigest()


def record_digest(record):
    return sha(canonical(record))


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"nonfinite JSON constant: {value}")


def _safe(value):
    if type(value) in (int, float):
        number(value, "JSON number")
    elif type(value) is list:
        for member in value:
            _safe(member)
    elif type(value) is dict:
        for key, member in value.items():
            text(key, "JSON key")
            _safe(member)
    else:
        require(value is None or type(value) in (str, bool), "non-JSON value")


def parse_json(data, *, max_bytes, canonical_required=False):
    integer(max_bytes, "max_bytes", 1)
    require(type(data) is bytes and len(data) <= max_bytes, "bounded JSON bytes required")
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
        _safe(value)
        encoded = canonical(value)
    except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as error:
        raise ValueError(f"unsafe JSON: {error}") from error
    require(not canonical_required or encoded == data, "canonical JSON byte encoding required")
    return value


def absolute(value, name):
    text(value, name)
    require(Path(value).is_absolute(), f"{name}: absolute path required")
    return value


def read_regular(path, maximum):
    """Bound allocation and refuse blocking devices/FIFOs/final symlinks; locators confer no identity."""
    integer(maximum, "maximum file bytes", 1, sys.maxsize - 1)
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        return _read_descriptor(fd, maximum)
    finally:
        os.close(fd)


def _read_descriptor(fd, maximum):
    integer(maximum, "maximum file bytes", 1, sys.maxsize - 1)
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum, "bounded regular file required")
    with os.fdopen(fd, "rb", closefd=False) as handle:
        data = handle.read(maximum + 1)
    require(len(data) <= maximum, "file exceeds byte bound")
    return data


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _open_directory(name, *, dir_fd=None):
    fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=dir_fd)
    try:
        require(stat.S_ISDIR(os.fstat(fd).st_mode), "directory descriptor required")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _open_store_root(root):
    """Pin every existing absolute directory component; never follow a replaced parent symlink."""
    parts = Path(absolute(str(root), "store root")).parts
    fd = _open_directory(parts[0])
    try:
        for component in parts[1:]:
            child = _open_directory(component, dir_fd=fd)
            os.close(fd)
            fd = child
    except BaseException:
        os.close(fd)
        raise
    return fd


def validate_store_root(root):
    """Validate even an unlabelled run's existing root; frame reads take their own fresh descriptor anchor."""
    fd = _open_store_root(root)
    os.close(fd)


def read_frame(root, raw_sha256, *, expected_bytes, compressed_limit, raw_limit):
    """One bounded zlib stream, exact BGRA length/digest; never creates/sweeps a store."""
    digest(raw_sha256, "rawSha256")
    integer(expected_bytes, "expected frame bytes", 1, sys.maxsize - 1)
    integer(raw_limit, "raw byte bound", 1, sys.maxsize - 1)
    integer(compressed_limit, "compressed byte bound", 1, sys.maxsize - 1)
    require(expected_bytes <= raw_limit, "expected frame exceeds raw byte bound")
    with ExitStack() as descriptors:
        root_fd = _open_store_root(root)
        descriptors.callback(os.close, root_fd)
        shard_fd = _open_directory(raw_sha256[:2], dir_fd=root_fd)
        descriptors.callback(os.close, shard_fd)
        frame_fd = os.open(raw_sha256 + ".zlib", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                           dir_fd=shard_fd)
        descriptors.callback(os.close, frame_fd)
        packed = _read_descriptor(frame_fd, compressed_limit)
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(packed, expected_bytes + 1)
        require(len(raw) == expected_bytes, "decompressed frame length mismatch")
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                "one complete zlib stream without trailing/concatenated data required")
    except zlib.error as error:
        raise ValueError("invalid zlib frame") from error
    require(sha(raw) == raw_sha256, "frame raw digest mismatch")
    return raw
