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

## Finding 2: additive U4 proposal trace clarification, before code (2026-10-24)

The coordinator accepted one additive ED-12 engineering event under FR-022: `proposal-created`, emitted by the
U4 proposer, requiring `proposalId` and the actual proposal payload digest. The already specified
`proposal-received` remains at the actual gate/manager receiver. Labelling the U4 emission as receipt would misstate
the direction and would not establish the required U4/U6/U5 trace. Existing objective/proposal/authorization/
transition binding ids join the events offline; no cross-run Argus causation is added. This changes the evidence
vocabulary only, with no authority, scientific parameter or evaluation signal. Record this clarification before
adding that kind to the implementation.

## Finding 3: initial structural probe, routed WP-04 source identity (2026-10-24)

The first small structural probe refused the genuine `ChassisZone.step` output. Inspection confirmed that WP-04
changes the routed record's payload `source` to `chassis-zone`, retaining the original arbiter in `route`; it does not
retain `source=functional-arbiter`. The new adapter had assumed the latter. Correct the adapter to require the actual
unchanged owner shape/source for each variant (direct arbiter versus routed chassis), before repeating the probe.
No WP-04 source, wire record or route will be changed.

## Finding 4: implementation and bounded verification (2026-10-24)

The candidate implements the closed role records, projected expected/received/payload source separation, explicit
URN-to-wire aliases and matching schema documents. F14 is an explicit authorization/gate-state union. WP-04 direct
and routed brake requests keep their actual owner members/source/route; WP-13 selector and three-member perception
provenance stay unchanged. Other legacy productive aliases name the existing owner schema; their validators remain
with those owners, and the new generic consumer refuses them rather than claiming to validate their semantics.

The ED-12 adapter accepts an already-open Argus writer, explicitly selected local roles and admitted engineering
byte bound. Its root event omits causation, later events use actual acknowledged local IDs, failed appends poison
the adapter, and source references carry only message IDs/digests. Genuine Argus writer/reader fixtures cover all
23 event kinds, the U4/U6/U5 chain, U5/U2 passive MRC receipt, comparator absence of U6, duplicate claims, foreign
causation, byte/source-reference refusal and failure poisoning. These Argus fixtures are written but **not run**
while the full platform regression owns execution. Unit-entry opening and admitted projection composition remain
14f; monitor, supervisor, gate, objective, manager and verifier semantics remain later increments. No process
isolation, deadline, scientific threshold or protocol approval is claimed by this typed contract.

The manager authority term is regenerated in all eight arm/form combinations. The local extension profile's enum
was updated to the accepted term so validation can recognize it. Existing pins and `check_topology.py` are unchanged;
`MANAGER_INPUTS`, selector chain and permitted outputs remain covered. The nine generated/profile document byte
hash pairs are recorded in `docs/evidence/wp14a-generated-document-digests.json`; these are **not** compiled-plan
semantic digests. Actual compilation, semantic-digest recording and all authority checks remain queued.

Performed: 74 direct deterministic structural/identity cases (including closed records, spoofing, F14, exact WP-04
and WP-13 preservation, generated-schema equality and forbidden imports); equality of all eight generated forms
against the pinned generator; seven Python syntax checks; whitespace diff check. The initial WP-04 routed-source
failure and correction are documented in finding 3. A later verification invocation passed the generator arguments
in the wrong order, was corrected without code changes, and then passed. No pytest runner, actual Argus execution,
CARLA, model inference or download was performed. Independent review and the full owning suite remain mandatory
before acceptance or merge.

Next full-suite command, from this worktree's `automotive/assured-aeb`, only after the active platform regression:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 XVERSE_AEB_SENSOR_SITE=/dev/shm/xverse-aeb-sensor-20261024/venv/lib/python3.13/site-packages XVERSE_PLATFORM_PROFILES=/tmp/codex-xverse-review-20261024-q93eotxv/xdl/profiles /dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider tests --tb=short
```

## Finding 5: independent full-suite finding and fixture repair design (Codex, 2026-10-24)

Exact `2a71f2eb98b14cdc29c4ffcccd3598c0c919e32f` gives **9 failed, 478 passed in 33.13 s**, no skips.
The nine genuine Argus cases fail at adapter construction: the fixture opens its accepted Argus run without
`clocks`. The platform API derives `declared_domains` from explicit `open_run(clocks=...)`, not from plan time
domains. Thus the adapter correctly rejects an undeclared simulator domain. Full log/receipt are in the thesis
`review/codex-successor-verification-20261024/role-contract/`; no acceptance follows.

Repair design, before code: keep the product refusal. In the genuine test fixture explicitly declare its TEST-ONLY
carla-simulation/ns clock with the opening value, and register every opened writer for teardown before adapter
construction so an initialization failure cannot leave it open. Add a genuine writer control proving missing/wrong
domain declarations are refused without claiming the writer, and that explicitly matching clocks allow an event
to be written/read. No topology time-domain, epoch, scientific clock mapping or product default changes.
Repeat the full owning suite and actual eight-form authority checks; independently review this successor.

The independent source review has additionally inspected typed closed records, projected versus received versus
payload sources, unchanged productive aliases, acknowledged-only local causation, append-failure poisoning,
one-writer claims and digest-only offline joins. No additional source blocker is recorded at this pass. Unit-entry
opening/projection wiring remains14f; supplying a local allow-list does not independently prove process isolation.
