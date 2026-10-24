# Terminal arbiter contract (WP-15 DN-1 candidate)

`FunctionalArbiter` accepts the existing five-member selector command from the configuration manager.
The first accepted `S_MRC_REQUESTED` selector snapshots the value of the last emitted WP-04 brake request,
after clamping. This includes zero: an earlier positive raw/valid request cannot replace a more recent emitted
zero. Live requests in the entry inbox cannot change that snapshot. Each subsequent call emits exactly the
same value, with the current simulator origin and next request sequence, through the caller-owned horizon.

No live source, source loss or ordinary bounded-hold expiry changes terminal output. Terminal lockout refuses
operational/recovery selectors, including a later selector in the entry inbox. A newer duplicate terminal
selector is refused as `selector-terminal-already-entered`; it cannot resnapshot or advance the accepted
selector identity. Existing malformed, source and replay refusals remain. No arm label is consumed.

When terminal is the first selector before any emission, the existing initial neutral 0.0 output is held.
Evidence explicitly identifies `initial-neutral-no-prior-emission`; it never describes a nonexistent prior
emission. This empty-history boundary disposition was recorded under delegation and flagged for author review
before implementation in `review-wp13-terminal.md`. If an earlier cycle emitted zero without a selector,
that is actual emission history and receives `last-emitted-request` provenance.

The five-member productive `brake-request` stays unchanged. Offline `arbiter-cycle` evidence uses
`kind=terminal-entry-value-hold`, the output `value`, and `terminalHoldProvenance` (`last-emitted-request` or
`initial-neutral-no-prior-emission`). Operational cycles have null provenance. Terminal cycles have no selected
interface or live source sequence/origin/state/reason, null `rawValue`, and `clamped=false`: the snapshot was
already clamped when emitted. Refused selectors are recorded in the existing `refusals` list.

`arbiter.mrcSource` is removed from the declaration and explicitly refused if an older projection supplies it.
No replacement policy value is required: the accepted structure is the entry-value hold. The arbiter still
requires `arbiter.requestFreshnessNs` and `arbiter.holdWindowNs` for operational behavior. Their consumed-entry
digest consequently changes; later unit composition must admit projections from this revised declaration.
No final projection membership, protocol identifier/value, source pin or numeric freeze is supplied here.

This candidate executes no external MRC and does not wire the supervisor, manager or passive request sink.
AD-14 still counts every eligible cycle after an MRC request as missing, regardless of held value. Neither a
positive hold nor neutral output earns availability or adaptation credit. Source review and the complete
owning/assembled suites remain required; no live or scientific acceptance is implied.
