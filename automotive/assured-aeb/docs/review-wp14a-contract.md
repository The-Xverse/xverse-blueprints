# WP-14 increment 14a: role contracts, source identity and ED-12

Candidate: `candidate/phase8-wp14a-20261024`, from blueprints main
`8bd0d3497b5cfe9d444985796dbd9c1e300dd9de`. Direct offline engineering increment under the recorded 2026-10-24
standing delegation and the coordinator's scoped instruction. No acceptance or merge yet.

Inputs: thesis `specs/002-assured-aeb/design/wp14-roles.md` (accepted design, including the accepted U2 ED-12
amendment), `decisions.md` WP-14 DN-1 to DN-9 and the WP-15 amended-design acceptance; accepted amended
`design/wp15-graph.md`; WP-12 topology and authority checks; WP-04 brake vocabulary; WP-13 schema strings and
three-member perception provenance; accepted Argus `EvidenceStore.open_run`, `EvidenceRun.append_event` and
`EvidenceStore.read_run`. The canonical note is unchanged at blob `ba244ddb`; the coordinator's freshness check
has no incoming note change. Existing main-checkout AGENTS modifications are preserved by the isolated worktree.

## Finding 1: design before implementation

1. **Runtime contract module.** `assured_aeb/role_contract.py`, standard library only. It holds the new closed role
   records and binding shapes, explicit projected endpoint bindings and an explicit mapping between XDL payload URNs
   and the existing `assured-aeb.<name>/1` schema strings. F14 explicitly permits the new `gate-state` record on its
   authorization interface; the XDL URN remains unchanged and both variants are recorded. New records use source,
   per-producer sequence and simulator origin. Binding fields follow WP-14 §2.2; semantic authorization/single-use,
   guard, deadline and supervisor decisions belong to 14b–14e/WP-15, not this increment.
2. **Source identity.** Each endpoint binding states interface, expected producer and consumer from its admitted
   unit projection. Consumption checks the separately supplied received producer against that expectation, then
   checks the record's payload source against the declared source vocabulary. Payload self-identification is not a
   transport attestation. Critical command chains are closed independently of caller-supplied expected identities;
   an IVI, router or proposer cannot become a gate or manager merely by changing payload source. This is typed
   identity checking, not cryptographic role isolation inside a shared process.
3. **Compatibility.** Preserve the exact WP-04 five-member arbiter request, routed chassis request and node command/
   status variants; do not add an envelope member to them. Preserve WP-13's selector command and three-member
   perception provenance. Legacy schema aliases are explicit references to their owning validators/contracts rather
   than a silent rewrite of the wire vocabulary. No runtime import of offline topology, protocol, oracle, arm table,
   fault schedule or training data. The binding is passed explicitly and contains only its selected interface pair.
4. **Role record shapes.** Define proposal, objective, goal-model, qualified-evidence, diagnostic-verdict, assessment,
   authorization/gate-state, forced-command, transition-request/verdict, configuration-state, aeb-status and mrc-request.
   Records are closed and all fields are required; genuinely unavailable evidence uses explicit nulls. Typed evidence
   metadata is separate from raw productive records; provenance digest maps never alter the existing perception
   record. Objective vocabulary and consumed evidence values remain role-specific validations for later increments.
   Publish matching JSON Schema descriptions from the same runtime definitions, with the XDL URN as `$id` and the
   actual schema string as `properties.schema.const`. No numeric protocol default is introduced.
5. **ED-12 writer.** `assured_aeb/role_events.py` accepts an already-open genuine Argus writer, its selected unit and
   local role allow-list, and a required maximum record byte bound supplied from admitted engineering limits. It never
   reads a full experiment plan. Unit-entry opening/projection composition remains 14f. One adapter may claim an Argus
   writer; a duplicate claim is refused. U2/U4/U5/U6 are supported without importing an arm label; a comparator fixture
   opens only its actual units. Emit annotation events under `io.xverse.assured-aeb.role-events`, version 1, using the
   accepted `append_event` API. Source references contain actual message ids/digests and binding ids; full payloads,
   images and pixel bytes cannot be passed as extension fields. Event kind, local role and all fields are checked.
6. **Causation/failure.** The first event omits causation. Later events refer only to already successfully appended
   local event ids; a foreign or fabricated root id is refused. Cross-unit links are only message/binding identifiers
   and digests for offline joins. Append failure poisons the adapter (no automatic retry or invented receipt). A
   caller-supplied record byte cap and Argus's own bounds are engineering serialization constraints, not scientific
   thresholds. A separate offline join helper validates local chains and groups shared binding/message ids.
7. **Topology rename.** Change only the configuration manager's `authorityClass` from `executor` to
   `configuration-manager`. Regenerate every arm in both forms using the existing recorded pins, not host refresh.
   Keep `MANAGER_INPUTS`, command chains, allocation and permitted outputs unchanged. Record before/after generated
   file hashes; actual compiled-plan digests and all authority/topology checks are required after serialization with
   the active platform regression. No topology or policy widening is implied.
8. **Verification.** Add closed-shape/missing/extra/nonfinite tests, spoofed received/payload identities, legacy
   vocabulary/provenance preservation, F14 union coverage, no forbidden runtime imports, real Argus writer/reader
   fixtures for every event kind and per-unit causal chains, independent-unit offline joins including U2 MRC receipt,
   duplicate writer claims, foreign causation, append failure and byte-bound refusals, plus rename/pin invariants.
   While the full platform regression is active, run only syntax and small stdlib probes. No pytest, CARLA, inference,
   download, acceptance or merge. The full owning suite and independent implementation review remain required.
