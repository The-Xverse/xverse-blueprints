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
