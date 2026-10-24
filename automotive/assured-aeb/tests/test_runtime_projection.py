"""WP-17b own-unit projection checks; all parameter/membership values TEST-ONLY."""

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from assured_aeb import projection_builder as B
from assured_aeb import protocol as P
from assured_aeb import runtime_projection as R
import test_protocol as F

ROLES = {"fusion-risk-aeb": "adas-hpc", "proposer": "adas-hpc", "radar-fallback": "vc-functional"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture():
    record = F.record()
    record["entries"]["fallback.oddMaxEgoSpeedMps"] = F.entry(12.0, category="runtime")
    obj = F.principal(record)
    table = {"schema": B.TABLE_SCHEMA, "protocolRecordSha256": obj.digest, "roles": {
        "fusion-risk-aeb": {"unit": "adas-hpc", "identifiers": ["aeb.marginM"]},
        "proposer": {"unit": "adas-hpc", "identifiers": ["aeb.marginM"]},
        "radar-fallback": {"unit": "vc-functional", "identifiers": ["fallback.oddMaxEgoSpeedMps"]}}}
    return obj, table


def build(obj, table, roles=ROLES):
    data = F.encoded(table)
    return B.build(obj, data, table_sha256=sha(data), expected_roles=roles)


def test_one_projection_per_unit_contains_only_the_union_of_its_role_entries():
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    assert set(outputs) == {"adas-hpc", "vc-functional"}
    assert receipt["tableSha256"] == sha(F.encoded(table))
    for unit, expected in [("adas-hpc", {"aeb.marginM": 0.5}),
                           ("vc-functional", {"fallback.oddMaxEgoSpeedMps": 12.0})]:
        projected = R.verified_projection(outputs[unit], expected_sha256=receipt["units"][unit]["sha256"],
                                          expected_unit=unit, protocol_record_sha256=obj.digest,
                                          identifiers=list(expected))
        assert projected == {"schema": R.SCHEMA, "protocolRecordSha256": obj.digest, "unit": unit, "entries": expected}
        assert set(projected) == {"schema", "protocolRecordSha256", "unit", "entries"}


@pytest.mark.parametrize("kind", ["omitted", "extra", "moved", "duplicate-id"])
def test_mutated_role_membership_is_refused_even_with_a_new_content_hash(kind):
    obj, table = fixture()
    if kind == "omitted":
        table["roles"].pop("proposer")
    elif kind == "extra":
        table["roles"]["unknown"] = {"unit": "adas-hpc", "identifiers": []}
    elif kind == "moved":
        table["roles"]["proposer"]["unit"] = "vc-functional"
    else:
        table["roles"]["proposer"]["identifiers"] *= 2
    with pytest.raises(R.ProjectionRefused):
        build(obj, table)


@pytest.mark.parametrize("category", ["oracle", "scenario", "fault", "metric"])
def test_forbidden_category_cannot_be_added_to_the_runtime_table(category):
    obj, table = fixture()
    rec = F.record()
    rec["entries"]["fallback.oddMaxEgoSpeedMps"] = F.entry(12.0, category="runtime")
    rec["entries"]["extra.forbidden"] = F.entry(1.0, category=category)
    obj = F.principal(rec)
    table["protocolRecordSha256"] = obj.digest
    table["roles"]["proposer"]["identifiers"].append("extra.forbidden")
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-FORBIDDEN"):
        build(obj, table)


@pytest.mark.parametrize("namespace", sorted(B.FORBIDDEN_NAMESPACES))
def test_forbidden_namespace_remains_refused_if_mislabeled_as_runtime(namespace):
    _, table = fixture()
    rec = F.record()
    rec["entries"]["fallback.oddMaxEgoSpeedMps"] = F.entry(12.0, category="runtime")
    identifier = namespace + ".privateValue"
    rec["entries"][identifier] = F.entry(1.0, category="runtime")
    obj = F.principal(rec)
    table["protocolRecordSha256"] = obj.digest
    table["roles"]["proposer"]["identifiers"].append(identifier)
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-FORBIDDEN"):
        build(obj, table)


def test_reviewed_table_hash_and_protocol_binding_are_required():
    obj, table = fixture()
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-DIGEST"):
        B.build(obj, F.encoded(table) + b" ", table_sha256=sha(F.encoded(table)), expected_roles=ROLES)
    table["protocolRecordSha256"] = "f" * 64
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-DIGEST"):
        build(obj, table)


@pytest.mark.parametrize("kind", ["unit", "protocol", "missing", "extra", "member", "digest"])
def test_runtime_reader_checks_every_admitted_boundary(kind):
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    record = json.loads(outputs["adas-hpc"])
    if kind == "unit":
        record["unit"] = "vc-functional"
    elif kind == "protocol":
        record["protocolRecordSha256"] = "f" * 64
    elif kind == "missing":
        record["entries"].clear()
    elif kind == "extra":
        record["entries"]["oracle.hidden"] = 1.0
    elif kind == "member":
        record["faultSchedule"] = []
    data = F.encoded(record)
    expected = sha(data) if kind != "digest" else "0" * 64
    with pytest.raises(R.ProjectionRefused):
        R.verified_projection(data, expected_sha256=expected, expected_unit="adas-hpc",
                              protocol_record_sha256=obj.digest, identifiers=["aeb.marginM"])


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e9999}', b'[]', b'\xff'])
def test_runtime_json_rejects_ambiguity_and_nonfinite_values(raw):
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-JSON"):
        R.verified_projection(raw, expected_sha256=sha(raw), expected_unit="adas-hpc",
                              protocol_record_sha256="a" * 64, identifiers=[])


def test_projection_values_are_private_and_publication_is_exclusive(tmp_path):
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    directory = tmp_path / "bundle"
    pins = {"expected_table_sha256": sha(F.encoded(table)), "protocol_record_sha256": obj.digest}
    B.write_bundle(directory, outputs, receipt, **pins)
    assert {p.name for p in directory.iterdir()} == {"adas-hpc.json", "vc-functional.json", "projection-pins.json"}
    for unit, data in outputs.items():
        assert (directory / (unit + ".json")).read_bytes() == data
    with pytest.raises(FileExistsError):
        B.write_bundle(directory, outputs, receipt, **pins)
    changed = dict(outputs)
    changed["adas-hpc"] += b" "
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-DIGEST"):
        B.write_bundle(tmp_path / "bad", changed, receipt, **pins)
    assert not (tmp_path / "bad").exists()


def test_runtime_module_cannot_import_whole_record_or_offline_modules():
    source = Path(R.__file__).read_text()
    tree = ast.parse(source)
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0  # no package-relative offline dependency
            roots.add(node.module.split(".")[0])
    assert roots <= {"__future__", "copy", "hashlib", "json", "math", "re", "typing"}
    assert not roots & {"protocol", "projection_builder", "topology", "oracle"}


# Publication successor cases; every table, pin and value below is TEST-ONLY.

def publication_pins(obj, table):
    # Independent admitted inputs, deliberately not reconstructed from the receipt under test.
    return {"expected_table_sha256": sha(F.encoded(table)), "protocol_record_sha256": obj.digest}


@pytest.mark.parametrize("kind", [
    "missing-table", "extra-member", "wrong-schema", "missing-units", "units-list", "foreign-protocol",
    "foreign-table", "bad-table-hash", "bad-record-hash", "missing-unit", "extra-unit",
    "wrong-identifiers", "duplicate-identifiers", "identifiers-object", "missing-unit-hash",
    "missing-unit-identifiers", "extra-unit-member", "bad-unit-hash",
])
def test_publication_refuses_incoherent_receipt_before_creating_directory(tmp_path, kind):
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    changed = copy.deepcopy(receipt)
    unit = changed["units"]["adas-hpc"]
    if kind == "missing-table":
        changed.pop("tableSha256")
    elif kind == "extra-member":
        changed["extra"] = True
    elif kind == "wrong-schema":
        changed["schema"] = "other/1"
    elif kind == "missing-units":
        changed.pop("units")
    elif kind == "units-list":
        changed["units"] = []
    elif kind == "foreign-protocol":
        changed["protocolRecordSha256"] = "f" * 64
    elif kind == "foreign-table":
        changed["tableSha256"] = "f" * 64
    elif kind == "bad-table-hash":
        changed["tableSha256"] = "invalid"
    elif kind == "bad-record-hash":
        changed["protocolRecordSha256"] = "invalid"
    elif kind == "missing-unit":
        changed["units"].pop("vc-functional")
    elif kind == "extra-unit":
        changed["units"]["unknown"] = dict(unit)
    elif kind == "wrong-identifiers":
        unit["identifiers"] = ["oracle.notSent"]
    elif kind == "duplicate-identifiers":
        unit["identifiers"] *= 2
    elif kind == "identifiers-object":
        unit["identifiers"] = {"aeb.marginM": True}
    elif kind == "missing-unit-hash":
        unit.pop("sha256")
    elif kind == "missing-unit-identifiers":
        unit.pop("identifiers")
    elif kind == "extra-unit-member":
        unit["filePath"] = "other.json"
    elif kind == "bad-unit-hash":
        unit["sha256"] = "invalid"
    directory = tmp_path / "refused"
    with pytest.raises(R.ProjectionRefused):
        B.write_bundle(directory, outputs, changed, **publication_pins(obj, table))
    assert not directory.exists()


@pytest.mark.parametrize("kind", ["schema", "protocol", "unit", "missing-identifier", "extra-identifier", "member", "json"])
def test_publication_decodes_output_even_if_its_receipt_hash_was_updated(tmp_path, kind):
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    record = json.loads(outputs["adas-hpc"])
    if kind == "schema":
        record["schema"] = "other/1"
    elif kind == "protocol":
        record["protocolRecordSha256"] = "f" * 64
    elif kind == "unit":
        record["unit"] = "vc-functional"
    elif kind == "missing-identifier":
        record["entries"].clear()
    elif kind == "extra-identifier":
        record["entries"]["extra.value"] = 1
    elif kind == "member":
        record["foreign"] = True
    outputs["adas-hpc"] = b'{"duplicate":1,"duplicate":2}' if kind == "json" else F.encoded(record)
    receipt["units"]["adas-hpc"]["sha256"] = sha(outputs["adas-hpc"])
    directory = tmp_path / "refused"
    with pytest.raises(R.ProjectionRefused):
        B.write_bundle(directory, outputs, receipt, **publication_pins(obj, table))
    assert not directory.exists()


@pytest.mark.parametrize("field", ["expected_table_sha256", "protocol_record_sha256"])
def test_publication_requires_each_explicit_admitted_pin(tmp_path, field):
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    pins = publication_pins(obj, table)
    pins.pop(field)
    directory = tmp_path / "missing-pin"
    with pytest.raises(TypeError):
        B.write_bundle(directory, outputs, receipt, **pins)
    assert not directory.exists()


@pytest.mark.parametrize("field", ["expected_table_sha256", "protocol_record_sha256"])
@pytest.mark.parametrize("value", [None, "invalid", "f" * 64])
def test_publication_checks_the_external_pin_not_just_the_receipt(tmp_path, field, value):
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    pins = publication_pins(obj, table)
    pins[field] = value
    directory = tmp_path / "wrong-pin"
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-DIGEST"):
        B.write_bundle(directory, outputs, receipt, **pins)
    assert not directory.exists()


def test_reserved_unit_name_is_refused_before_bundle_creation_and_by_builder(tmp_path):
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    record = json.loads(outputs["adas-hpc"])
    record["unit"] = "projection-pins"
    payload = F.encoded(record)
    collision = {"projection-pins": payload}
    changed = copy.deepcopy(receipt)
    changed["units"] = {"projection-pins": {"sha256": sha(payload), "identifiers": ["aeb.marginM"]}}
    directory = tmp_path / "reserved"
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-UNIT"):
        B.write_bundle(directory, collision, changed, **publication_pins(obj, table))
    assert not directory.exists()
    roles = {role: "projection-pins" if unit == "adas-hpc" else unit for role, unit in ROLES.items()}
    for role, definition in table["roles"].items():
        definition["unit"] = roles[role]
    with pytest.raises(R.ProjectionRefused, match="PROJECTION-UNIT"):
        build(obj, table, roles=roles)


def test_publication_uses_checked_snapshots_if_caller_mutates_after_validation(tmp_path, monkeypatch):
    obj, table = fixture()
    outputs, receipt = build(obj, table)
    expected_outputs, expected_receipt = dict(outputs), F.encoded(receipt)
    directory = tmp_path / "snapshot"
    mkdir = Path.mkdir
    def mutate_after_validation(path, *args, **kwargs):
        if path == directory:
            outputs.clear()
            receipt["units"].clear()
            receipt["tableSha256"] = "f" * 64
        return mkdir(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", mutate_after_validation)
    B.write_bundle(directory, outputs, receipt, **publication_pins(obj, table))
    assert (directory / "projection-pins.json").read_bytes() == expected_receipt
    assert {p.name for p in directory.iterdir()} == {*(unit + ".json" for unit in expected_outputs), "projection-pins.json"}
    for unit, data in expected_outputs.items():
        assert (directory / (unit + ".json")).read_bytes() == data


def test_publication_receipt_and_table_schemas_match_the_closed_contract():
    import jsonschema
    obj, table = fixture()
    _, receipt = build(obj, table)
    directory = Path(__file__).resolve().parents[1] / "protocol"
    receipt_validator = jsonschema.Draft202012Validator(json.loads((directory / "projection-pins.schema.json").read_text()))
    assert not list(receipt_validator.iter_errors(receipt))
    for changed in ({**receipt, "unknown": True}, {k: v for k, v in receipt.items() if k != "tableSha256"}):
        assert list(receipt_validator.iter_errors(changed))
    reserved = copy.deepcopy(receipt)
    reserved["units"] = {"projection-pins": receipt["units"]["adas-hpc"]}
    assert list(receipt_validator.iter_errors(reserved))
    table_validator = jsonschema.Draft202012Validator(json.loads((directory / "projection-table.schema.json").read_text()))
    table["roles"]["proposer"]["unit"] = "projection-pins"
    assert list(table_validator.iter_errors(table))
