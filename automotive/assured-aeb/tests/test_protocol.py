"""WP-17a synthetic policy/declaration tests. ALL values are TEST-ONLY.

No fixture is a real protocol freeze, approval, method choice or experimental
parameter. Datetimes exercise ordering, not a scientific timing window.
"""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from assured_aeb import protocol as P
from assured_aeb.protocol_audit import numeric_literals

BEFORE = "2026-10-01T00:00:00Z"
PILOT = "2026-10-02T00:00:00Z"
DECLARED = "2026-10-03T00:00:00Z"
ACCEPTED = "2026-10-04T00:00:00Z"
PRINCIPAL = "2026-10-05T00:00:00Z"


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def entry(value, status="final", category="policy"):
    return {"value": value, "unit": "TEST-ONLY", "source": {"kind": "policy", "reference": "TEST-ONLY decision"},
            "status": status, "category": category}


def record():
    values = ("TEST-ONLY metric", 0.1, 0.2, [11, 12], "TEST-ONLY invalid rule", "TEST-ONLY candidate method")
    entries = {name: entry(value) for name, value in zip(P.H2_IDENTIFIERS, values)}
    entries[P.RUNTIME_LIMIT] = entry({"path": "lite", "m1Admitted": False, "limitation": "TEST-ONLY non-M1 limit"})
    entries["aeb.marginM"] = entry(0.5, category="runtime")
    return {"schema": P.RECORD_SCHEMA, "recordId": "TEST-ONLY", "declaredAt": DECLARED, "entries": entries}


def approval(when):
    return {"reference": "TEST-ONLY approval reference", "acceptedAt": when}


def policy_pin(rec):
    return {"sha256": P.policy_digest(rec["entries"]), "acceptance": approval(BEFORE)}


def pin(rec, *, policy=True):
    return {"schema": P.PIN_SCHEMA, "recordSha256": sha(encoded(rec)), "acceptance": approval(ACCEPTED),
            "prePilotPolicy": policy_pin(rec) if policy else None}


def principal(rec=None, authority=None, pilot=PILOT):
    rec = record() if rec is None else rec
    authority = pin(rec) if authority is None else authority
    return P.Protocol.principal(encoded(rec), encoded(authority), started_at=PRINCIPAL, first_pilot_at=pilot)


def test_final_freeze_can_follow_pilot_with_unchanged_pre_pilot_policy():
    # Full freeze follows the pilot that determines repetitions; the policy subset was already approved.
    obj = principal()
    assert obj.value("aeb.marginM") == 0.5
    assert obj.metadata() == {"runKind": "principal", "protocolRecordSha256": sha(encoded(record())),
                              "engineeringDataOnly": False, "runtimePathLimit": record()["entries"][P.RUNTIME_LIMIT]["value"]}


def test_no_pilot_requires_an_explicit_null_policy_pin():
    rec = record()
    assert principal(rec, pin(rec, policy=False), pilot=None).kind == "principal"
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-PILOT-POLICY"):
        principal(pilot=None)


def test_absent_record_and_unsigned_pin_have_distinct_refusals():
    with pytest.raises(P.ProtocolRefused) as caught:
        P.Protocol.principal(b"", encoded(pin(record())), started_at=PRINCIPAL, first_pilot_at=PILOT)
    assert caught.value.code == "PROTOCOL-ABSENT"
    with pytest.raises(P.ProtocolRefused) as caught:
        P.Protocol.principal(encoded(record()), b"", started_at=PRINCIPAL, first_pilot_at=PILOT)
    assert caught.value.code == "PROTOCOL-PIN-ABSENT"
    authority = pin(record())
    authority["acceptance"] = None
    with pytest.raises(P.ProtocolRefused) as caught:
        principal(authority=authority)
    assert caught.value.code == "PROTOCOL-UNSIGNED"


def test_digest_pins_exact_bytes_not_a_reparsed_equivalent():
    rec = record()
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-DIGEST"):
        P.Protocol.principal(encoded(rec) + b"\n", encoded(pin(rec)), started_at=PRINCIPAL, first_pilot_at=PILOT)


@pytest.mark.parametrize("missing", P.H2_IDENTIFIERS)
def test_each_required_h2_identifier_is_checked(missing):
    rec = record()
    rec["entries"].pop(missing)
    authority = pin(record())
    authority["recordSha256"] = sha(encoded(rec))
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-H2-MISSING"):
        principal(rec, authority)


@pytest.mark.parametrize("status", ["provisional", "unresolved"])
def test_nonfinal_entry_blocks_principal_but_not_declaration_parsing(status):
    rec = record()
    rec["entries"]["aeb.marginM"]["status"] = status
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-NONFINAL"):
        principal(rec)
    obj = P.Protocol.characterisation(encoded(rec), expected_digest=sha(encoded(rec)), started_at=PRINCIPAL)
    assert obj.metadata()["engineeringDataOnly"] is True
    if status == "provisional":
        assert obj.value("aeb.marginM") == 0.5
    else:
        with pytest.raises(P.ProtocolRefused, match="PROTOCOL-NONFINAL"):
            obj.value("aeb.marginM")


@pytest.mark.parametrize("value", ["TODO: author decision", "NEEDS DATA", {"nested": "pending measurement"}])
def test_placeholder_cannot_be_promoted_by_changing_only_status(value):
    rec = record()
    rec["entries"]["aeb.marginM"]["value"] = value
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-NONFINAL"):
        principal(rec)


@pytest.mark.parametrize("value", [None, "", "TODO: margin", True, 10**1000])
def test_unusable_final_h2_number_is_refused_without_crashing(value):
    rec = record()
    rec["entries"]["h2.nonInferiorityMargin"]["value"] = value
    authority = pin(record())
    authority["recordSha256"] = sha(encoded(rec))
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-H2-UNRESOLVED"):
        principal(rec, authority)


@pytest.mark.parametrize("limit", [None, "M1", {}, {"path": "lite", "m1Admitted": True, "limitation": "TEST"},
                                    {"path": "lite", "m1Admitted": False, "limitation": ""}])
def test_runtime_limit_must_state_the_approved_non_m1_boundary(limit):
    rec = record()
    if limit is None:
        rec["entries"].pop(P.RUNTIME_LIMIT)
    else:
        rec["entries"][P.RUNTIME_LIMIT]["value"] = limit
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-RUNTIME-LIMIT"):
        principal(rec)


def test_late_acceptance_and_policy_drift_are_refused():
    rec = record()
    authority = pin(rec)
    authority["acceptance"]["acceptedAt"] = "2026-10-06T00:00:00Z"
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-CHRONOLOGY"):
        principal(rec, authority)
    authority = pin(rec)
    authority["prePilotPolicy"]["acceptance"]["acceptedAt"] = DECLARED
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-PILOT-POLICY"):
        principal(rec, authority)
    authority = pin(rec)
    rec["entries"]["h2.minimumBenefit"]["value"] = 0.3
    authority["recordSha256"] = sha(encoded(rec))
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-PILOT-POLICY"):
        principal(rec, authority)


def test_missing_pre_pilot_pin_is_refused():
    rec = record()
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-PILOT-POLICY"):
        principal(rec, pin(rec, policy=False))


def test_missing_identifier_has_no_default_and_reads_are_private():
    obj = principal()
    seeds = obj.value("h2.seeds")
    seeds.append(999)
    assert obj.value("h2.seeds") == [11, 12]
    obj.metadata()["runtimePathLimit"]["m1Admitted"] = True
    assert obj.metadata()["runtimePathLimit"]["m1Admitted"] is False
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-IDENTIFIER"):
        obj.value("absent.identifier")
    with pytest.raises(AttributeError):
        obj.kind = "characterisation"
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-ADMISSION"):
        P.Protocol(record(), "a" * 64, "principal")


def test_pilot_declaration_needs_h2_approval_but_not_final_freeze():
    rec = record()
    rec["declaredAt"] = BEFORE
    rec["entries"]["aeb.marginM"]["status"] = "provisional"
    rec["entries"]["h2.repetitions"] = entry(None, status="unresolved")
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-PILOT-POLICY"):
        P.Protocol.characterisation(encoded(rec), expected_digest=sha(encoded(rec)), started_at=PILOT, is_pilot=True)
    obj = P.Protocol.characterisation(encoded(rec), expected_digest=sha(encoded(rec)), started_at=PILOT,
                                     pilot_policy=policy_pin(rec), is_pilot=True)
    assert obj.kind == "characterisation" and obj.value("aeb.marginM") == 0.5


def test_characterisation_declared_after_run_is_refused():
    rec = record()
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-CHRONOLOGY"):
        P.Protocol.characterisation(encoded(rec), expected_digest=sha(encoded(rec)), started_at=BEFORE)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e9999}', b'[]', b'\xff'])
def test_ambiguous_or_nonfinite_json_is_refused(raw):
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-JSON"):
        P.Protocol.characterisation(raw, expected_digest=sha(raw), started_at=PRINCIPAL)


def test_missing_file_is_a_refusal(tmp_path):
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-ABSENT"):
        P.read_bytes(tmp_path / "absent.json")


def test_closed_schemas_match_synthetic_valid_examples():
    import jsonschema
    directory = Path(__file__).resolve().parents[1] / "protocol"
    for filename, example in [("record.schema.json", record()), ("pin.schema.json", pin(record()))]:
        schema = json.loads((directory / filename).read_text())
        validator = jsonschema.Draft202012Validator(schema)
        assert not list(validator.iter_errors(example))
        changed = {**example, "unknown": True}
        assert list(validator.iter_errors(changed))


def test_numeric_literal_exceptions_are_source_bound_and_never_hide_new_constants(tmp_path):
    path = tmp_path / "unit.py"
    path.write_text("structural = 2\n")
    findings = numeric_literals(tmp_path, ["unit.py"], [])
    assert len(findings) == 1 and findings[0]["literal"] == "2"
    exception = {k: v for k, v in findings[0].items() if k != "literal"}
    exception.update(reason="TEST-ONLY structural fixture", reviewReference="TEST-ONLY review")
    assert numeric_literals(tmp_path, ["unit.py"], [exception]) == []
    changed = copy.deepcopy(exception)
    changed["literalSha256"] = "0" * 64
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-AUDIT"):
        numeric_literals(tmp_path, ["unit.py"], [changed])
    path.write_text("structural = 2\nscientific = 7\n")
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-AUDIT"):
        numeric_literals(tmp_path, ["unit.py"], [exception])
    exception["fileSha256"] = sha(path.read_bytes())
    assert [x["literal"] for x in numeric_literals(tmp_path, ["unit.py"], [exception])] == ["7"]
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-AUDIT"):
        numeric_literals(tmp_path, [], [exception])


def test_audit_rejects_paths_outside_scope(tmp_path):
    with pytest.raises(P.ProtocolRefused, match="PROTOCOL-AUDIT"):
        numeric_literals(tmp_path, ["../other.py"], [])
