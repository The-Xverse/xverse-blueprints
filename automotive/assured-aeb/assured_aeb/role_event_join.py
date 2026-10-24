"""Offline-only ED-12 grouping of actual Argus records by binding/reference ids.

No runtime module imports this helper. Caller-selected runs must already belong
in the same experiment evidence package; an equal id alone does not prove that.
"""
from __future__ import annotations

from .role_contract import ContractError
from .role_events import EXTENSION


def join_role_events(records_by_unit):
    """Validate local chains and return shared binding/message groups, no causation rewrite."""
    groups = {}
    for unit, records in records_by_unit.items():
        seen, run_id = set(), None
        for record in records:
            payload = record.get("extensions", {}).get(EXTENSION)
            if payload is None:
                continue
            if payload.get("unit") != unit:
                raise ContractError("a role-event record belongs to another unit")
            if run_id is None:
                run_id = record.get("runId")
            if record.get("runId") != run_id or record.get("eventId") in seen:
                raise ContractError("duplicate event or mixed runs within one unit")
            cause = record.get("causationId")
            if cause is not None and cause not in seen:
                raise ContractError("missing or foreign within-run causation")
            seen.add(record["eventId"])
            item = {"unit": unit, "runId": run_id, "eventId": record["eventId"], "kind": payload["kind"], "payloadSha256": payload["payloadSha256"]}
            for name, value in payload["bindings"].items():
                groups.setdefault((name, value), []).append(item)
            if payload["kind"] in ("mrc-request", "mrc-request-received"):
                groups.setdefault(("mrc-request", payload["bindings"]["requestId"], payload["payloadSha256"]), []).append(item)
            for ref in payload["sourceRefs"]:
                groups.setdefault(("message", ref["messageId"], ref["sha256"]), []).append(item)
    return groups
