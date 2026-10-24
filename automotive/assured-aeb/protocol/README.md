# Protocol representations (WP-17a)

These closed schemas describe the record and its approval pin. There is no real record or accepted pin here.
The authoritative record will be authored in the thesis package `specs/002-assured-aeb/protocol/` and copied here
by digest after the relevant approval. The schemas do not fix a numeric value, projection membership or method.

`assured_aeb.protocol.Protocol.principal` checks exact record bytes against the externally approved pin, final
statuses, six H2 policy entries, the AD-21 path limit and chronology. The pin is a trusted decision reference,
not a cryptographic signature. A changed record requires a new pin. If pilot data exist, its stable H2 subset
must match a separate pre-pilot policy digest and approval. Full freeze may follow the pilot that determines
repetitions. The loader never authenticates the decision reference or validates the cited measurement itself.

`Protocol.characterisation` checks a caller-supplied digest and pre-run declaration. It permits provisional
values but refuses unresolved values when consumed. Its metadata always says engineering data only. For D-6,
`is_pilot=True` additionally requires the stable H2 policy approval before pilot start; the 17f harness must
bind that flag to run kind. This method does not grant live-run authorization.

Runtime units receive only their parameter projection, never these whole records or this offline loader.
WP-17b fixes the per-role projection table. The numeric AST audit needs an explicit complete file inventory and
source-bound reviewed structural exceptions. It cannot classify scientific meaning or prove global scope by
itself; qualitative literals and parameter provenance also need the reviewed 17b/AD-27 audit.

See `../docs/review-wp17a-protocol.md` for scope, decisions, verification and pending gates.

The UTC representation is `YYYY-MM-DDTHH:MM:SS[.digits](Z|+00:00)` with a valid Gregorian date/time and ordinary
seconds. Arbitrary fractional precision is compared exactly using integer date/time components and normalised
fractional digits, without float conversion or microsecond truncation. Equal fractions with trailing zeroes compare
equal. Unsupported syntax, other offsets and leap-second forms are refused; the representation imposes no scientific
window, deadline or precision cap.

The explicit placeholder vocabulary is checked recursively in JSON values. After repeatedly removing balanced
bracket (`[]`, `()`, `{}`, `<>`), quote and Markdown emphasis/strike/inline-code wrappers, a leading `TODO`, `TBD`
or `NEEDS DATA` token is unresolved. `PENDING` is recognised only as a complete status, a `PENDING:` directive, or
an exact pending-status phrase for measurement, author decision, validation, approval, data, review or freeze.
Checks are case-insensitive. Ordinary prose containing pending (including a sentence beginning “Pending proposals”)
is not rejected by that word alone. This is a supported marker vocabulary, not detection of every missing human decision.

`Protocol.entry(identifier)` gives the offline projection builder a private copy of that single checked entry's
value and metadata (unit, source, status, category). It shares the mode/status/placeholder and missing-identifier
gates with `value(identifier)`. Reading entry metadata selects no runtime projection membership and exposes no whole
record; runtime units still receive only the separately reviewed WP-17b projections.
