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
