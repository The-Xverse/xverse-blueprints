"""Frame store interface (WP-09 increment #1; review-wp09-labels finding 1 §1.6).

Raw verified frames are stored losslessly with ``zlib`` under ``<root>/<sha[:2]>/<sha>.zlib``, keyed by their
``rawSha256``. The root (the proposed loop10 dataset path of design §2), the free-space floor (TODO: author decision)
and the compression level are required, with no default. Records carry digests and sizes, never bytes.

Durability (review-wp09-labels finding 4, LOW-2): the shard directory is fsynced after the rename. Stale ``.tmp-*``
files left by an interrupted write are removed when the store is opened. The store assumes a single writer: the
free-space check and the write are not atomic with respect to other writers.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import tempfile
import zlib

HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SHARD = re.compile(r"[0-9a-f]{2}\Z")
TEMP_PREFIX, TEMP_SUFFIX = ".tmp-", ".zlib"


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class FrameStoreError(RuntimeError):
    pass


class FrameStore:
    def __init__(self, root: str | os.PathLike, *, free_space_floor_bytes: int, compression_level: int,
                 frame_length: int | None) -> None:
        root = Path(root)
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("root must be an existing absolute directory (no default)")
        if type(free_space_floor_bytes) is not int or free_space_floor_bytes < 0:
            raise ValueError("free_space_floor_bytes must be a non-negative integer (TODO: author decision; no default)")
        if type(compression_level) is not int or not 0 <= compression_level <= 9:
            raise ValueError("compression_level must be an integer in [0, 9]")
        if frame_length is not None and (type(frame_length) is not int or frame_length <= 0):
            raise ValueError("frame_length must be a positive integer or None")
        self.root, self.floor, self.level, self.frame_length = root, free_space_floor_bytes, compression_level, frame_length
        self.swept = self._sweep()

    def _sweep(self) -> int:
        """Remove stale temporary files of interrupted writes in the shard directories (single writer, at open)."""

        removed = 0
        for shard in self.root.iterdir():
            if not (shard.is_dir() and not shard.is_symlink() and SHARD.match(shard.name)):
                continue
            stale = [entry for entry in shard.iterdir() if entry.name.startswith(TEMP_PREFIX)
                     and entry.name.endswith(TEMP_SUFFIX) and entry.is_file() and not entry.is_symlink()]
            for entry in stale:
                entry.unlink()
            if stale:
                _fsync_dir(shard)
            removed += len(stale)
        return removed

    def path(self, raw_sha256: str) -> Path:
        if not (isinstance(raw_sha256, str) and HEX64.match(raw_sha256)):
            raise FrameStoreError("rawSha256 must be a lowercase SHA-256 hex digest")
        return self.root / raw_sha256[:2] / f"{raw_sha256}.zlib"

    def put(self, raw: bytes, raw_sha256: str) -> dict:
        """Store one verified frame; return ``{rawSha256, rawBytes, storedBytes, status}`` (never the bytes)."""

        target = self.path(raw_sha256)
        if hashlib.sha256(raw).hexdigest() != raw_sha256:
            raise FrameStoreError("frame bytes do not match rawSha256")
        if self.frame_length is not None and len(raw) != self.frame_length:
            raise FrameStoreError(f"frame length {len(raw)} differs from the declared {self.frame_length}")
        if target.exists():
            existing = self.get(raw_sha256)  # verifies the stored copy
            if existing != raw:  # unreachable for a matching digest; kept as a guard
                raise FrameStoreError("stored frame differs")
            return {"rawSha256": raw_sha256, "rawBytes": len(raw), "storedBytes": target.stat().st_size, "status": "present"}
        packed = zlib.compress(raw, self.level)
        target.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(target.parent).free - len(packed) < self.floor:
            raise FrameStoreError("refused: the write would fall below the free-space floor")
        fd, temp = tempfile.mkstemp(dir=target.parent, prefix=TEMP_PREFIX, suffix=TEMP_SUFFIX)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(packed)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
            _fsync_dir(target.parent)  # make the rename durable (LOW-2)
        except BaseException:
            if os.path.exists(temp):
                os.unlink(temp)
            raise
        return {"rawSha256": raw_sha256, "rawBytes": len(raw), "storedBytes": len(packed), "status": "stored"}

    def get(self, raw_sha256: str) -> bytes:
        """Return the verified raw frame bytes (in process only; never written to evidence)."""

        raw = zlib.decompress(self.path(raw_sha256).read_bytes())
        if hashlib.sha256(raw).hexdigest() != raw_sha256:
            raise FrameStoreError("stored frame fails its digest")
        return raw
