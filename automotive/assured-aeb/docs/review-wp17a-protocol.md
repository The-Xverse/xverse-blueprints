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

## Finding 3: independent read-only review (Codex `/root/review_wp15`, 2026-10-24), CHANGES REQUIRED

Input: `c80774360d60c7b1278be1fc5927fd58141e25cd`. Reviewed both complete modules, both JSON Schemas,
representation README and all synthetic tests against WP-17 O-1 and the explicitly recorded ordering amendment.
No product repair was made during this review. No pytest/heavy process was run while the full platform regression
was active. AST parsing passed for both modules and `tests/test_protocol.py`.

### R17a-1, MAJOR: ordinary bracketed project placeholders pass principal admission

`protocol._placeholder()` checks only the raw string's starting word. With an otherwise valid synthetic record and
pins, final `h2.statisticalMethod = "[NEEDS DATA]"` or `"[TODO: author decision]"` passes `policy_digest()` and
`Protocol.principal()` and is returned unchanged by identifier. Plain `"TODO: citation needed"` is refused as a
control. These are explicit unresolved project markers, not actual selected final method values. Principal admission
must not be enabled by assigning a final status to a bracketed marker. The same helper is used for nested values
and characterisation consumption, so its supported marker contract should be explicit and tested across those paths.

Recommendation: recognise the explicit TODO/NEEDS DATA/TBD marker vocabulary through ordinary bracket/Markdown
wrappers and nested values. Preserve legitimate final prose that merely contains an ordinary word such as
“pending” in a sentence. State exactly which markers are recognised; do not claim automatic recognition of every
unresolved human decision. Add negative wrapped/nested cases and positive prose controls, without choosing a real
statistical method or supplying a scientific value.

### R17a-2, MEDIUM: timestamp truncation can reverse required approval chronology

`protocol._time()` accepts arbitrary fractional-second strings through `datetime.fromisoformat()`, which retains
only microseconds. Reproduced on the pinned CPython 3.13.13 interpreter:
- pre-pilot approval `2026-10-02T00:00:00.000000002Z` is admitted for pilot start
  `2026-10-02T00:00:00.000000001Z`;
- final approval `2026-10-03T00:00:00.000000001Z` is admitted for record declaration
  `2026-10-03T00:00:00.000000002Z`;
- the control with policy approval one second after pilot start is refused as `PROTOCOL-PILOT-POLICY`.

The first two are out of order but compare equal after truncation. The JSON Schemas do not restrict fractional
precision, so they do not establish representability either. This is approval metadata representation, not a new
scientific deadline or simulator-time parameter.

Recommendation: explicitly select and document a lossless timestamp representation. Either reject precision the
comparison type cannot retain, or compare arbitrary fractional seconds exactly. Align the schemas and tests with
that choice. Do not silently round a later approval into an earlier/equal instant. Cover record declaration/final
acceptance, acceptance/principal start and pre-policy acceptance/pilot start, with ordered controls.

### Boundaries assessed without a new blocker

- Exact original record bytes are hashed before parsing. Duplicate JSON members and non-finite floating values are
  refused; large finite JSON integers remain a typed-consumer responsibility as explicitly designed.
- The external pin is a trusted decision-reference input, not an authenticated signature. The loader and README
  state that limitation; this review does not infer author identity, validate a cited source or create a real pin.
- The stable H2 subset includes metadata and provenance in its canonical digest. Final freeze may follow the pilot,
  while the stable policy acceptance precedes pilot data, as required by the ordering amendment.
- Principal/characterisation APIs and metadata remain distinct; characterisation does not create principal or live
  execution authority. The 17f harness must still bind `is_pilot` and actual pilot chronology to run kind; caller
  omission is not an implementation of that future integration gate.
- The literal scanner reports numeric AST constants for an explicit file inventory and checks source/literal-bound
  exception drift. It does not establish global inventory completeness or qualitative-parameter provenance, and the
  README correctly carries those 17b/AD-27 gates. A small fixture is not a global no-scientific-literal proof.
- Entry reads and returned principal-limit metadata are private copies. No runtime unit imports this whole-record
  loader in this increment; future projection membership remains 17b's responsibility.

### Reproduction and deferred verification

Small standard-library probes used CPython 3.13.13 with `-S -s -B`, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONPATH`
pointing only at this blueprint. Every fixture value and timestamp was TEST-ONLY. Positive valid-policy admission
and plain-TODO/one-second-late refusal controls passed; the two defects above remain reproducible.

The complete owning suite is **not run by this reviewer** and remains required after repairs:
`env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 XVERSE_PLATFORM_PROFILES=<rc.1>/xdl/profiles
XVERSE_AEB_SENSOR_SITE=<pinned-sensor-site> /dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider tests --tb=short`
from `automotive/assured-aeb`, after the full platform regression releases the heavy-test slot. A focused run is
`... -m pytest -q -p no:cacheprovider tests/test_protocol.py --tb=short` under the same environment.

Record dispositions/design before code, then independently re-review repaired code and source-bound suite evidence.
This candidate is not accepted or merged. Real protocol values, author approval, AD-27, projection membership,
principal/live admission, M1 and scientific claims remain outside this review.

## Finding 4: separately recorded successor design before code (2026-10-24)

The coordinator dispositioned both independent findings before repair and requested one identifier-access addition
for the later offline projection builder. This successor changes no scientific parameter, policy selection,
projection membership, approval authority or runtime import boundary.

### R17a-1 marker contract

Unwrap balanced ordinary brackets (`[]`, `()`, `{}`, `<>`), quote marks and Markdown emphasis/strike/code wrappers,
repeatedly, then recognise case-insensitive leading **tokens** `TODO`, `TBD` or `NEEDS DATA`. Nested JSON object/list
values receive the same check. A token boundary is required, so unrelated words that merely start with those letters
are not markers. Preserve `PENDING` as an explicit whole status, a `PENDING:` directive, or exactly a status phrase
with measurement, author decision, validation, approval, data, review or freeze. Merely containing the word pending,
including ordinary prose beginning “Pending proposals ...”, is not a placeholder. Tests will state both the supported
marker forms and non-marker prose. This is an explicit vocabulary check, not a classifier for arbitrary unresolved
human decisions.

### R17a-2 exact UTC chronology representation

Compare UTC instants exactly at arbitrary fractional-second precision. Accept the strict supported form
`YYYY-MM-DDTHH:MM:SS[.digits](Z|+00:00)` with a valid Gregorian date/time; reject malformed/unsupported syntax rather
than silently normalising it. Validate integer date/time components with the standard library, but store comparisons
as the integer-second component tuple followed by fractional digits with trailing zeroes removed. Lexicographic
comparison of those normalised fractional strings preserves exact order and equality without float conversion or
microsecond truncation. No rounding, precision cap or coarser scientific timing policy is introduced.

Align each timestamp property in the record/pin JSON Schemas and the README with that representation. Regress late
pre-policy acceptance below a microsecond, final acceptance before declaration below a microsecond, acceptance after
principal start below a microsecond, equal fractions with trailing zeroes, and the existing one-second-late control.

### Identifier-only metadata access for WP-17b

Add `Protocol.entry(identifier)` for the offline projection builder. It returns a private deep copy of exactly that
entry's existing metadata and value after the same missing/status/placeholder checks used by `value(identifier)`.
Make `value` delegate to the checked single-entry path so the gates cannot drift. The builder can then read category,
status and provenance without accessing `_record`; it still must fix its own reviewed allow-lists in WP-17b and never
expose the complete record or import this loader in runtime units. Add private-copy, missing-identifier and nonfinal
entry tests in both modes. This interface addition does not choose an identifier's projection membership.

Implementation follows this separate design commit. Only small standard-library probes, AST/schema JSON parsing and
whitespace checks may run while the platform regression is active; pytest remains queued. A separate independent
review of the repaired delta and the owning suite are required before acceptance.
