"""Offline numeric-literal inventory with explicitly reviewed structural exceptions.

This is a conservative numeric AST scan, not an automatic scientific classification
or proof of complete scope. The caller must supply the reviewed runtime/harness
inventory; WP-17b/AD-27 own its completeness and qualitative-parameter audit.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from .protocol import ProtocolRefused


def numeric_literals(root: Path, files: list[str], exceptions: list[dict]) -> list[dict]:
    root = Path(root).resolve()
    if len(set(files)) != len(files):
        raise ProtocolRefused("PROTOCOL-AUDIT", "duplicate inventory path")
    permitted = {}
    members = {"file", "fileSha256", "line", "column", "literalSha256", "reason", "reviewReference"}
    for entry in exceptions:
        if (not isinstance(entry, dict) or set(entry) != members
                or type(entry["line"]) is not int or type(entry["column"]) is not int
                or not isinstance(entry["reason"], str) or not entry["reason"].strip()
                or not isinstance(entry["reviewReference"], str) or not entry["reviewReference"].strip()):
            raise ProtocolRefused("PROTOCOL-AUDIT", "malformed or unreviewed exception")
        key = entry["file"], entry["line"], entry["column"]
        if key in permitted:
            raise ProtocolRefused("PROTOCOL-AUDIT", "duplicate structural exception")
        permitted[key] = entry
    pending, used = [], set()
    for name in files:
        path = root / name
        if Path(name).is_absolute() or not path.resolve().is_relative_to(root):
            raise ProtocolRefused("PROTOCOL-AUDIT", "inventory escapes reviewed root")
        data = path.read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()
        source = data.decode()
        for node in ast.walk(ast.parse(source, filename=name)):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float, complex):
                text = ast.get_source_segment(source, node)
                literal_hash = hashlib.sha256(text.encode()).hexdigest()
                key = name, node.lineno, node.col_offset
                entry = permitted.get(key)
                if entry is not None:
                    if entry["fileSha256"] != file_hash or entry["literalSha256"] != literal_hash:
                        raise ProtocolRefused("PROTOCOL-AUDIT", "structural exception drift")
                    used.add(key)
                else:
                    pending.append({"file": name, "fileSha256": file_hash, "line": node.lineno,
                                    "column": node.col_offset, "literalSha256": literal_hash, "literal": text})
    if set(permitted) != used:
        raise ProtocolRefused("PROTOCOL-AUDIT", "unused exception or missing inventory file")
    return pending
