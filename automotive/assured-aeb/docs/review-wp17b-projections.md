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
