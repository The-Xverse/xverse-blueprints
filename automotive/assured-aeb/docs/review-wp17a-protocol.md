# WP-17a protocol record and loader: review and implementation record

Candidate: `candidate/phase8-wp17a-protocol-20261024`, from blueprints main
`8bd0d3497b5cfe9d444985796dbd9c1e300dd9de`. Offline engineering only, under the author's recorded delegation
(thesis decisions §G, WP-17 DN-1 to DN-9). No real protocol record, principal/live execution, scientific value,
cryptographic signature, acceptance or merge is created here. The existing midnight rc.1 soak is unchanged.

## Finding 1: implementation design before code, 2026-10-24

Inputs: thesis `specs/002-assured-aeb/design/wp17-support.md` O-1 and 17a; FR-024/FR-028; V17/V35;
`review/freeze-readiness-20261024.md` §2; decisions AD-21, AD-22a, AD-27 and the WP-17 delegated row.
The canonical dynamic note is unchanged at blob `ba244ddb7df388386455524ab7667d4a1e86d5a3`; parent session
read it completely and revalidated a fresh fetch and hash before this continuation.

### Conflict to resolve explicitly before implementation

WP-17 O-1 says the *record's* acceptance cannot follow the first pilot; freeze-readiness §2 explicitly places the
D-6 pilot before the final freeze, because repetitions are measured from that pilot. Those statements cannot both
mean full AD-27 acceptance. Preserve the approved ordering: the policy subset required before the pilot is
accepted before pilot data; full AD-27 freeze follows characterisation and precedes principal evidence.
This amendment changes no numeric policy and needs a delegated disposition in the thesis decision record before
code. The loader will validate two pins: the final record, and the stable H2 policy subset against its earlier
acceptance. It will not require pilot-derived repetitions to exist before the pilot that measures them.

### Record and pin contracts

- Standard-library module `assured_aeb.protocol` and closed JSON Schemas under `protocol/`.
- Record members: `schema`, `recordId`, `declaredAt`, `entries`. Each dotted identifier maps to exactly
  `value`, `unit`, `source`, `status`, `category`; source holds exactly `kind` and `reference`.
  Status is `final`, `provisional` or `unresolved`. Categories distinguish runtime, oracle, scenario, fault,
  metric and policy data for the later projection generator. No actual entries/values are authored here.
- JSON is parsed with duplicate-member rejection and rejects non-finite numbers. Finite JSON integers remain
  valid until a typed consumer validates its representability. UTC timestamps must carry an explicit zone.
  Entry access returns a private copy, so callers cannot mutate the accepted record through a returned value.
- The final pin holds exactly schema, `recordSha256`, `acceptance`, and `prePilotPolicy` (nullable before pilot).
  Acceptance is a non-empty decision reference plus `acceptedAt`. This is the DN-1 digest/reference convention,
  not signature authentication; the pin is an externally approved input and the loader never manufactures it.
- Pre-pilot policy binds a digest of the six H2 entries, including their metadata, plus its own acceptance.
  Identifier constants: `h2.safetyMetric`, `h2.nonInferiorityMargin`, `h2.minimumBenefit`, `h2.seeds`,
  `h2.invalidRunRule`, `h2.statisticalMethod`. These are implementation names, not selected scientific values.
- AD-21 identifier: `runtime.pathLimit`, a required final declaration `{path: lite, m1Admitted: false, limitation: <non-empty text>}` copied into admitted principal-run metadata. This encodes the already decided path boundary, not a new protocol value.
- A principal admission refuses: absent bytes; absent pin; mismatched digest; malformed JSON/record/pin; unresolved
  or provisional entries; any missing H2 member; absent/empty AD-21 limit; an acceptance after principal start;
  and, if pilot data exist, missing/mismatched H2 policy pin or policy acceptance after first pilot start.
  H2 entries must contain actual final values, not TODO/NEEDS DATA/pending placeholders. No default value exists.
- Characterisation access is separate: exact caller-supplied digest and declaration before run start are required;
  provisional entries may be consumed, unresolved entries may not. Its metadata is explicitly engineering data
  with `runKind=characterisation`. This grants no AD-22a execution authority and never returns principal metadata.
  A D-6 caller must separately validate the pre-pilot policy pin; 17f will wire that requirement by run kind.
- JSON Schemas define representation only. Python enforces digest, chronology, presence and use-mode rules.

### Literal audit and downstream boundary

The literal scanner will examine explicitly named Python files, report numeric AST constants, and accept only
exact source-bound structural exceptions with a reason and review reference. A changed exception or unused
exception is rejected. Global scientific coverage requires the complete runtime/harness file inventory and
projection membership fixed in 17b/AD-27; a small synthetic scanner fixture is not claimed as global coverage.
No runtime unit imports this offline record loader: units retain only their FR-028 parameter projections.
The loader is exported at module scope only; no CLI will open a file supplied by a runtime message.

### Verification and maturity

Meaningful table-driven tests cover every refusal above, exact bytes versus altered bytes, private-copy reads,
characterisation/principal separation, temporal ordering around the pilot, and literal-exception drift.
All values are synthetic TEST-ONLY. Full owning suite and independent review follow. The platform regression
currently owns the heavy-test slot: implementation and syntax checks may proceed, pytest waits its turn.
SADS disposition: existing P8-T06 allocation is preserved; this is a partial FR-024/V17/V35 implementation,
not complete P8-T06, fitness or runtime projection delivery.

## Finding 2: implementation ready for independent review; full suite queued

Implemented `assured_aeb.protocol`, `protocol_audit`, closed record/pin schemas and representation documentation,
plus synthetic `tests/test_protocol.py`. Exact record-byte pins, final-entry/H2 presence gates, declared non-M1
metadata, stable pre-pilot H2 policy chronology, characterisation-only access, private-copy reads and numeric
literal inventory are represented. The ordering amendment is recorded in the thesis decision record and overlaid
on WP-17 O-1. No real record, pin, policy number or final projection membership was produced.

Performed: AST parsing of both modules and the test file; a tiny standard-library positive principal-admission
fixture plus changed-byte refusal; `git diff --check`. No pytest, numerical framework or live workload was run.
The platform full regression owns the heavy-test slot. Owning full-suite verification and independent re-review
remain required before acceptance. Global literal/provenance coverage and run-kind wiring remain 17b/17f gates;
the numeric scanner alone is deliberately not reported as a complete scientific-literal audit.
