# WP-17b runtime-parameter projection builder and reader

Candidate `candidate/phase8-wp17b-projections-20261024`, dependency WP-17a candidate `c807743` (unaccepted;
review successor must be integrated before testing/acceptance). No real projection table, membership freeze,
protocol value, run or principal admission is authored by this increment.

## Finding 1: design before code (2026-10-24)

Scope: accepted WP-17 O-2 and DN-7; FR-028/V21. Standard-library-only modules:
- `projection_builder`: OFFLINE, imports the accepted protocol API, reads an exact digest-bound reviewed table,
  and generates one projection per unit. It never runs inside a runtime unit.
- `runtime_projection`: RUNTIME, imports only the standard library. It checks the exact supplied projection digest,
  protocol-record digest, expected own unit and exact consumed identifier set. It returns the closed projection
  form already declared by WP-13 `parameters.Projection`, with no record/approval/evaluation metadata added.

The table has exactly schema, protocolRecordSha256 and roles. Every role maps to exactly its unit and its list of
consumed identifiers. Inputs include the externally pinned table SHA-256 and the reviewed expected role-to-unit map
from the runtime-plan inventory; they have no defaults. The builder refuses an omitted/extra role, moved role,
duplicate identifier within a role, altered table or a foreign protocol digest. Shared parameters consumed by two
roles in one unit are unioned, not leaked to another unit. A table mutation requires a new reviewed digest.

For every selected identifier, inspect the protocol's authoritative entry through a private-copy identifier API.
Reject oracle, scenario, fault and metric categories; permit runtime or policy only. Also reject controlled
forbidden namespaces (`h2`, `oracle`, `scenario`, `fault`, `metrics`, `metric`) even if metadata is mislabeled.
This is not semantic inference about arbitrary names: actual membership and classification remain the reviewed
AD-27 freeze and provenance audit. An unknown/misclassified identifier cannot be approved merely by passing a schema.
Status validation remains the protocol loader's mode-specific rule. A characterisation projection grants no
principal-evidence status; run-kind selection remains outside runtime data.

Generated file: {schema: assured-aeb.runtime-parameter-projection/1, protocolRecordSha256, unit, entries: id->value}.
The external pin receipt holds that file's SHA-256 and the table SHA-256; neither table nor full protocol is sent to
runtime units. Runtime readers receive their expected identifier list from their own role declarations and reject
any extra/missing identifier. Values are private copies. JSON rejects duplicate members and non-finite values.

Schemas and tests will cover exact role/unit membership, repeated shared parameters, category/namespace denial,
table and output mutation, own-unit mismatch, missing/extra keys, malformed JSON, private-copy reads, and an AST
import scan showing runtime code never imports the offline record/builder/oracle/topology modules. Fixtures are
TEST-ONLY. No actual table is filled until its membership is reviewed/fixed with AD-27.

The full V21 audit of process argv/environment/working directories/inbound flows is a composition obligation of
unit wiring, not proved by this file generator. The literal-audit mechanism from 17a requires a complete reviewed
inventory and exception list; this increment must not call an import-only check a complete provenance audit.

Full owning-suite verification and independent review are required before acceptance. The platform regression owns
the heavy test slot now; perform only syntax and tiny stdlib probes until it finishes. Source-bound test commands
and outstanding integration obligations must remain explicit in subsequent findings.

## Finding 2: source implementation, dependency review and suite pending

Implemented the offline builder, runtime-only reader, table schema, publication helper and synthetic tests.
The reader uses the existing four-member WP-13 projection representation and imports no offline thesis/protocol/
oracle/topology code. The builder's authoritative metadata access depends on WP-17a's reviewed `entry(identifier)`
private-copy API; integrate that successor before execution. The full V21 provenance and process-delivery audit,
actual membership table and global literal inventory remain explicitly open.

Performed AST parsing on both new modules and the test file and `git diff --check`. No pytest, generator execution,
real projection file, live run or protocol value is claimed. Full suite and independent source review are queued
after dependency integration and release of the platform regression's heavy-test slot.

## Finding 3: independent read-only review (Codex `/root/review_wp15`, 2026-10-24), CHANGES REQUIRED

Input: `2cdc8313c5f931e7baee9767499765374eb8f898` (builder implementation `0a2211d` with WP-17a successor).
Read findings 1 and 2, both complete modules, table schema, documentation and tests. No product repair or pytest
was performed during this review; the full platform regression still owns the heavy-test slot.

### R17b-1, MEDIUM: publication verifies payload hashes but not the receipt's claimed evidence binding

`write_bundle` checks matching unit inventory and each payload SHA-256, but never checks the closed receipt shape,
its schema, its table/protocol digest fields, or its identifier claims against decoded output. Tiny CPython 3.13.13
standard-library probes each successfully published a complete `projection-pins.json` after independently:
- deleting `tableSha256`;
- changing `protocolRecordSha256` to a foreign lowercase SHA-256;
- replacing the unit's identifier list with `oracle.notSent`, while the actual bytes still contained `aeb.marginM`.

The downstream own-unit reader still verifies its explicitly admitted file/protocol/id boundaries. These probes
demonstrate inconsistent published bundle evidence and possible late refusal, not a demonstrated runtime leak.
Nevertheless, the publication helper claims to preserve the generated receipt's file/table binding and already
checks post-build payload mutation; receipt mutation must not silently produce a seemingly complete bundle.

Recommendation: validate the closed receipt, digest types and decoded output schema/unit/protocol/exact identifier
set before creating the artifact directory. Compare receipt table and protocol hashes with explicit admitted pins
supplied by the caller; checking self-declared receipt hashes alone does not authenticate the reviewed table. Add
negative cases for each changed boundary and a positive fresh publication case. Preserve the existing external
approval trust boundary and the fact that a receipt grants neither execution nor scientific authority.

### R17b-2, LOW: a valid unit name collides with the reserved receipt filename

`projection-pins` passes the unit NAME grammar. With coherent bytes and receipt hashes for that unit, `write_bundle`
creates the directory, writes its unit payload as `projection-pins.json`, then raises `FileExistsError` trying to
write the receipt at the same path. The remaining file has the reserved receipt name but contains a projection.
The helper does not overwrite it, so this is a diagnosed partial artifact, not data loss or a successful publication.

Recommendation: reserve `projection-pins` explicitly and refuse it before directory creation, in the generator,
publication contract and schema where applicable. Test that this input leaves no artifact directory. No actual
current runtime unit is claimed to use that name.

### Boundaries assessed without a new blocker

The exact table bytes/digest and protocol digest are checked. External expected role membership rejects omitted,
extra or moved roles; each role's identifier list rejects duplicates, while same-unit roles intentionally share a
union. Actual identifier membership remains the reviewed table/AD-27 input and is not inferred from names.
Authoritative protocol metadata permits runtime/policy only and rejects oracle/scenario/fault/metric categories;
controlled forbidden namespaces remain denied even if relabelled runtime. Standard-library probes confirmed the
four category and six namespace denials, same-unit union and separate-unit output, and private returned values.

The runtime reader checks an independently supplied own unit, protocol hash, file hash and exact consumed ids, and
returns only the four-member projection form. Its AST import roots are exclusively standard-library modules; it
imports no full protocol, offline builder, oracle or topology. JSON ambiguity/non-finite checks are present.
Protocol mode/status checks are consumed through the private-copy entry API. Characterisation metadata does not
become a principal-evidence claim merely because a runtime projection can be generated.

These checks do not establish a complete process argv/environment/working-directory/inbound-flow provenance audit,
actual freeze membership or global literal coverage; the candidate correctly leaves those composition gates open.
The schemas describe representation, and the runtime caller's admitted pins/declarations remain required inputs.

### Verification and disposition

AST parsing passed for both new modules and the test file. The small publication probes used fresh temporary
subdirectories, synthetic TEST-ONLY records and no numerical framework; those probe directories were removed.
No pytest or live process was started. Record dispositions and a separate repair design before code; then obtain
independent re-review and exact-source suite evidence before acceptance.

Deferred focused check: from `automotive/assured-aeb`,
`env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider tests/test_runtime_projection.py --tb=short`.
Deferred owning suite: the same interpreter/options with `tests`, rc.1 `XVERSE_PLATFORM_PROFILES`, and the pinned
`XVERSE_AEB_SENSOR_SITE`, after the platform regression releases the heavy-test slot.
Candidate remains unaccepted and unmerged. No real table, protocol value, live/principal run, M1 or scientific claim
was created or validated by this review.

## Finding 4: separately recorded publication repair design before code (2026-10-24)

The coordinator dispositioned both findings before repair. This successor changes only mechanical publication
binding and reserved-name handling; actual projection membership, category classification, table approval, process
provenance and live/principal admission remain separate gates.

- Change `write_bundle` to require keyword-only `expected_table_sha256` and `protocol_record_sha256`, with no defaults.
  These are admitted caller inputs, independent of the receipt being checked; this helper cannot authenticate the
  table from a self-declared receipt. Validate both pin forms and require exact receipt equality.
- Define a closed projection-pins receipt contract/schema: schema, protocolRecordSha256, tableSha256 and units only;
  each unit has exactly sha256 and identifiers. Validate hash forms, own-unit names, duplicate-free identifier lists,
  and exact unit inventory. Decode each output through the standard-library own-unit reader using the admitted
  protocol digest and the receipt's expected unit/hash/identifiers, so mismatched schema/protocol/unit/id evidence
  is refused before publication.
- Snapshot the output mapping and canonical receipt bytes before writing, and perform all validation/serialization
  before creating the fresh directory. Bytes and the checked snapshot, rather than later caller mutations, are what
  is published. A later I/O failure remains an unaccepted diagnostic partial artifact; no durability/authentication
  claim is added. Existing bundle paths remain exclusive and are never overwritten.
- Reserve `projection-pins` as a publication unit name. Reject it in the reviewed role inventory/generator and in
  publication before directory creation, and express the reservation in the relevant table/receipt schemas.
  The reserved filename is a tool representation choice, not a scientific parameter or a new runtime unit.
- Regress missing/extra/wrong receipt members, malformed or mismatched admitted table/protocol pins, per-file hash,
  output schema/protocol/unit/identifier mismatch, receipt identifier mismatch, duplicate identifiers and the
  reserved name. Include coherent fresh publication and existing-directory non-overwrite controls. Every synthetic
  parameter and table membership remains TEST-ONLY. Update the documented API and all existing calls.

The finding 3 review was committed separately before this design. Implement next, run only AST/JSON parsing and tiny
standard-library probes while the platform regression owns the heavy-test slot, then commit the repair distinctly.
The coordinator will independently review the repaired delta; focused and full owning pytest remain queued.

## Finding 5: publication successor implemented; independent re-review and suite pending (2026-10-24)

Implemented finding 4 after separate design commit `13c0e9e` and the independent review commit `8eacecf`:
- `write_bundle` now requires explicit admitted `expected_table_sha256` and `protocol_record_sha256` arguments.
  It validates the closed receipt schema/member set, both expected pins and receipt digest fields, exact unit
  inventory and per-unit hash/identifier structure before creating a directory.
- Each output is decoded through `verified_projection` against its expected unit, protocol, digest and identifier
  list; hash-coherent but structurally foreign output cannot create an apparently complete bundle.
- Immutable output-byte and canonical receipt snapshots are checked and published, preventing caller mutations
  between validation and file writes from replacing the checked content. All serialisation and checks precede
  directory creation; an existing directory is never overwritten. Later I/O failure retains the stated unaccepted
  diagnostic-partial-artifact behaviour, without a new durability or table-authentication claim.
- `projection-pins` is reserved before generation/publication, and the table schema expresses that restriction.
  New `protocol/projection-pins.schema.json` defines the receipt's closed representation. `PROJECTIONS.md` documents
  the new required pins, their external trust boundary and fresh-publication semantics; existing calls are updated.

Added 7 regression test functions, parametrised across receipt members/pins/identifiers, decoded
output mutations, absent and wrong external pins, reserved names, publication snapshots and schema coherence.
The prior coherent-publication, changed-bytes and existing-directory controls remain. All membership and parameter
values are TEST-ONLY, and no real approved table or projection was authored.

Performed **17 tiny standard-library probes** on pinned CPython 3.13.13 with `-S -s -B` and blueprint-only
`PYTHONPATH`: positive exclusive publication; existing-path refusal; missing/foreign receipt pins, wrong receipt
identifiers/schema/extra fields and duplicates; independently wrong admitted pins; changed decoded output fields;
reserved-name refusal before any directory; generator reserved-name refusal; and controlled post-validation caller
mutation confirming the checked snapshots are what was written. Temporary probe artifacts were removed.
AST parsing passed for both modules and the test file; all schema files parse as JSON; `git diff --check` passes.

No pytest, full JSON Schema validator, numerical framework, live/principal run, acceptance or merge was executed.
The full platform regression owns the heavy-test slot. Run the finding 3 focused and full owning-suite commands
when released, then independently review this repaired delta and its exact-source evidence. Actual freeze membership,
full process-delivery provenance, global literal inventory and approval authority remain outside this successor.

## Finding 6: independent parent publication-successor review, PASS; full suite queued (2026-10-24)

Reviewed worker successor `02b787ca3726dc89cd5f21d7bcbcb48e9e63f1ed` against separate design `13c0e9e` and
independent finding 3. The parent did not author this publication repair. Closed receipt checks, external admitted
pins, decoded own-unit output/identifier validation and reserved-name denial all precede directory creation. The
checked byte/receipt snapshots are the objects published; an existing artifact is never overwritten. The receipt
remains evidence of these bindings, not authentication of author approval or full runtime provenance.

Independent tiny probes publish one valid bundle and reproduce all three original negative controls (missing table
pin, foreign protocol digest and inconsistent identifier receipt); each negative is refused before any directory
exists. The complete source/test/schema delta and snapshot mutation test were read. `git diff --check` passes.
No pytest or heavy check was started during platform regression. The publication findings are closed at source
review level; full schema/owning-suite verification is required before acceptance. Actual freeze membership and
the complete V21 process/data provenance audit remain open integration obligations.
