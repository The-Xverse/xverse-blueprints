# WP-09 increment #1 review log: perception labels, dataset manifest and frame store

Candidate: branch `candidate/phase8-wp09-labels-20261024`, from blueprints main `5f71cde`. This is a direct
engineering increment, and the log follows the same order:
1. findings come before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**Inputs.**
- Thesis `specs/002-assured-aeb`:
  - `design/wp09-training-pipeline.md` §1 (T-3, T-4, T-9, T-10, T-13), §2 (recording and the manifest), §3
    (labels, provenance and the split rule), §8 and §9 (increment #1);
  - `decisions.md`: the row "WP-09 training pipeline" (15:15; recommendations 1–7; WP-02b lateral-offset target in
    progress), §H P-2 and P-4.
- `xverse-compat` main `95e9e7a`, read-only:
  - `xverse_compat_carla/observe.py`: observer v2, schema `xverse-compat.evaluation-observer/2`;
    - frame records `{frame, simElapsedNs, roles: {role: entry}}`, where an entry has `status` (`observed`,
      `absent`, `ambiguous`, `not-in-snapshot`, `non-finite`), `location` [m], and `rotationDeg` [pitch, yaw,
      roll];
    - resolution lines `{resolution: true, frame, role, boundingBox: {extentM, locationM}}`, where `extentM` is
      the half-size and `locationM` the offset from the actor origin, in the actor frame;
  - `scenario.py` 31: `CAMERA_MOUNT = (1.5, 0.0, 2.4)` on the ego;
  - `xdl/descriptors/aeb-sim/carla-sensors.json`: camera 800 × 600 at 90°;
  - `docs/engineering/phase8/review-wp02.md` 344–348, R-2 as amended: the bumper-to-bumper gap uses
    `ego.locationM.x + ego.extentM.x` (ego front) and `target.extentM.x − target.locationM.x` (target rear).

**Scope.** Offline modules and tests only, on synthetic fixtures. No download, no CARLA, no live run; the soak's
loop10 paths are not touched, and the frame store is exercised on a temporary directory. This is engineering
evidence only.

## Finding 1: design (recorded at 15:25:01, before any code)

### 1.1 Label parameters (`assured-aeb.perception-label-params/1`, no defaults)
- **`corridor`:** `{halfWidthM, maxRangeM}`, both > 0. They are `TODO: author decision` (AD-02, WP-09).
- **`distanceBinEdgesM`:** a strictly increasing list of positive edges. It is `TODO: author decision`, after D-1
  and D-2.
- **`camera`:** `{mountM, fovDeg, width, height}`, the configured values: `CAMERA_MOUNT` and the descriptor's
  camera. They are sourced, not chosen here; a test asserts them against the cited values.
- `LabelParams.from_record` refuses a missing, extra or ill-typed member. The record digest goes into every label.

### 1.2 Geometry (CARLA's frame: x forward, y right, z up; yaw in degrees)
- **Planar model.** On the AD-04 flat straight road, pitch and roll are ignored, which is declared.
  - An actor's forward vector is `(cos yaw, sin yaw)` and its right vector `(−sin yaw, cos yaw)`.
  - A world point `p` in the ego frame is `((p − ego) · f, (p − ego) · r)`.
- **Footprints.** The ego front is at `x_front = ego.locationM.x + ego.extentM.x` in the ego frame. The target
  footprint is the rectangle with centre `origin + locationM.x · f_t + locationM.y · r_t`, half-sizes
  `extentM.x` and `extentM.y` and yaw `yaw_t`, expressed in the ego frame (four corners).
- **Distance.** The bumper-to-bumper longitudinal gap along the ego axis is `min(corner forward) − x_front`. For
  an aligned target this is R-2's expression, with `origin_x + locationM.x − extentM.x` as the target rear. A
  value ≤ 0 means the footprints overlap along the axis.
- **Corridor flag (footprint test).** The target footprint intersects the corridor rectangle
  `[x_front, x_front + maxRangeM] × [−halfWidthM, +halfWidthM]` in the ego frame, by a separating-axis test on
  the two rectangles.
- **Visibility test (separate field).**
  - The nearest point is the footprint corner that defines the distance. It is visible when it lies in the
    camera's horizontal field of view, `|atan2(y − mount.y, x − mount.x)| ≤ fov/2`, ahead of the camera.
  - In addition, the target's vertical span (`z ± extentM.z` about its box centre) must overlap the vertical
    field of view at that range. The vertical field of view is `2·atan(tan(fov/2) · height/width)`, the pinhole
    rule, which is a declared simplification.
  - There is no occlusion test: there is one target (design §3).
- **Obstacle label.** `obstacle = inCorridor and visible`. The two fields stay separate, so their disagreement
  is measurable (design §3).
- **Distance bin.**
  - `no-obstacle` when `obstacle` is false;
  - `overlap` when the distance is ≤ 0;
  - otherwise `bin-i` for `edges[i−1] ≤ d < edges[i]`, `bin-0` below the first edge, and `beyond` at or above
    the last edge.

### 1.3 Join and exclusions
- **Inputs.** The observer v2 file (header, resolution lines, frame records), the camera items of the run
  (`frame`, `rawSha256`), and the run declaration (`targetDeclared`).
- **Resolutions.** Extents come from the latest resolution line of each role at or before the frame. A role with
  no observed bounding box makes the frame unlabelled.
- **Unlabelled frames** are excluded and counted by reason:
  - no observer record for the camera frame;
  - the ego not `observed`;
  - a declared target that is not `observed` (absent, ambiguous, not-in-snapshot or non-finite);
  - a missing bounding box.
- **Runs without a target** (`targetDeclared: false`) give `no-obstacle` labels when the target role is `absent`.
  These are the negatives. Out-of-corridor negatives come from WP-02b and are labelled by the same corridor test.
- **The observer file must be evaluation-only.** The header has `evaluationOnly: true` and the observer v2
  schema, otherwise the join is refused.

### 1.4 Label record and provenance (`assured-aeb.perception-label/1`)
- **Members.** `frame`, `simElapsedNs`, `rawSha256`, `inCorridor`, `visible`, `obstacle`, `distanceM` (or
  `null`), `distanceBin`.
- **Provenance:**
  - `observerSha256`;
  - the 1-based `observerLine` of the frame record;
  - `labelCodeSha256`, the SHA-256 of the label module's source;
  - `labelParamsDigest`.
- **No pixels.** Labels are offline only. A test asserts that no runtime module (any module outside
  `assured_aeb/perception/` and `tests/`) imports the label code.

### 1.5 Dataset manifest (`assured-aeb.dataset-manifest/1`)
- **Members.** `schema`, `labelParamsDigest`, `evaluation` and `runs`.
  - `evaluation` is `{spawnPoint, seeds}`. The spawn point is 1 (P-2, K-9). The seed list is the P-4
    evaluation list, a required input with no default (TODO).
  - Each run is `{runId, seed, spawnPoint, segment, split, scenarioSha256, runParamsSha256, observerSha256,
    frames: [{frame, simElapsedNs, rawSha256}]}`.
- **Split rule (by run).** `split` ∈ {`training`, `calibration`, `test`} is a property of the run, and a frame
  carries none of its own.
- **`check_manifest` refuses:**
  - a run with the evaluation spawn point, or with an evaluation seed;
  - a seed used in two splits (P-4 disjoint lists);
  - a `rawSha256` in two runs, or in two splits;
  - a duplicate run id;
  - a malformed member.
- **Reported, not refused.** A segment shared between splits is reported, because "where the segment count
  allows" (design §3).
- **Identity.** The manifest's SHA-256 over its canonical JSON (sorted keys, no spaces, no NaN) is the dataset
  identity.
- **No pixels:** digests and counts only.

### 1.6 Frame store (interface; `assured-aeb.frame-store/1`)
- `FrameStore(root, freeSpaceFloorBytes, compressionLevel)`. All three are required, with no default. The
  floor is `TODO: author decision`. The root is the proposed loop10 dataset path (design §2), given by the
  caller and never defaulted; the tests use a temporary directory.
- **`put(raw, rawSha256)`:**
  - it verifies the digest, and refuses a length other than 1 920 000 when a frame length is declared (T-13);
  - it compresses with `zlib` and writes atomically: a temporary file in the same directory, `fsync`, then
    rename to `<root>/<sha[:2]>/<sha>.zlib`;
  - it refuses if the free space after the write would fall below the floor (`shutil.disk_usage`);
  - an existing identical entry is idempotent.
- **`get(rawSha256)`** decompresses and verifies the digest.
- **The returned records** carry digests and sizes, never bytes.

### 1.7 Files and tests (planned)
- **Package** `assured_aeb/perception/`: `__init__.py`, `labels.py`, `manifest.py` and `store.py`. Standard
  library only.
- **`tests/test_perception_labels.py`:**
  - hand-built observer v2 files: an aligned target ahead in the corridor; a lateral-offset target outside it; a
    yawed target; a target behind the camera's field of view; overlap; a missing resolution; an ambiguous
    target; a run without a target;
  - the bins at each edge;
  - provenance;
  - the parameter refusals;
  - the import-scan test.
- **`tests/test_perception_manifest.py`:** each manifest refusal, the digest's determinism and sensitivity, and
  the shared-segment report.
- **`tests/test_perception_store.py`:** put and get round trip on a temporary directory, the digest refusal,
  the floor refusal, idempotency, and no bytes in records.

### 1.8 Expected residuals
1. The corridor, the bin edges, the free-space floor and the evaluation seed list (AD-27, P-4).
2. Live data (D-3, E8-3a; increment #6).
3. The WP-02b lateral-offset target for the negatives.
4. The planar model: pitch and roll are ignored, and the pinhole vertical field of view.
5. The installed maps (P-2).

## Finding 2: implementation result (2026-10-24 15:28:57; commit `f095817`)

**What was added (standard library only).**
- `assured_aeb/perception/labels.py`: `LabelParams`, `parse_observer`, `geometry` (with the separating-axis
  `rectangles_intersect`), `distance_bin` and `label_run`.
- `assured_aeb/perception/manifest.py`: `build_manifest`, `check_manifest` and `manifest_digest`.
- `assured_aeb/perception/store.py`: `FrameStore`.
- **Tests:** `tests/test_perception_labels.py`, `tests/test_perception_manifest.py` and
  `tests/test_perception_store.py`: 56 tests.

**Commands.**
- The three new files: 56 passed.
- The whole blueprint suite with the rc.1 profiles: 227 passed.
- `check_topology.py`: exit 0. The WP-12 documents are unchanged.
- Host load 8.9, from other work on the host. No download, no CARLA, no live run. The frame store ran only on
  pytest temporary directories; the loop10 paths and the pinned live environment were not touched.

**Results against the design (finding 1).**

| Item | Result |
| --- | --- |
| Parameters §1.1 | The corridor, the bin edges and the camera come from an exact record with no defaults. Eight malformed variants are refused. The camera values are asserted equal to the configured ones (`CAMERA_MOUNT` (1.5, 0, 2.4); 800 × 600 at 90°). `label_run` refuses unvalidated parameters |
| Distance §1.2 | For an aligned target 30 m ahead: `(30 + 0.1 − 2.2) − (0 + 2.4) = 25.5` m, both bounding-box offsets as in WP-02 R-2. A target yawed by 90° uses its half-width as the longitudinal half-size (26.7 m). With ego and target both facing +y, the frame rotates correctly (25.5 m) |
| Corridor and visibility §1.2 | A lateral offset of 4 m is outside the corridor but visible, so it is not an obstacle: the WP-02b negative, with the two fields disagreeing measurably. A footprint touching the 1.5 m half-width counts. A target behind is neither in the corridor nor visible. A target 60 m below the camera is in the corridor but not visible (vertical field of view). A target at 120 m is beyond the corridor range |
| Bins §1.2 | `overlap` at d ≤ 0, then `bin-0` to `bin-2` at the edges, with the edge in the upper bin, and `beyond` from the last edge. `no-obstacle` whenever the obstacle flag is false |
| Join and exclusions §1.3 | A run without a target gives `no-obstacle` negatives. Ambiguous, non-finite and absent declared targets, a missing observer record, an unobserved ego and a missing bounding box are excluded and counted by reason. A header that is not evaluation-only v2 is refused |
| Provenance §1.4 | Each label carries the observer file's SHA-256, the 1-based line of its frame record (verified against the file), the SHA-256 of `labels.py` itself, the parameter-record digest and the joined `rawSha256`. No bytes |
| Offline only | An AST scan of every module outside `assured_aeb/perception/` and `tests/` (at least five modules) finds no import of the perception or label code |
| Manifest §1.5 | A good manifest is admissible. Its digest is the dataset identity: deterministic and sensitive to one frame digest. Refused: spawn point 1, an evaluation seed, a seed in two splits, a frame digest in two runs, a duplicate run id, an unknown split, missing run members, a frame with its own split member, a malformed digest, and an empty or altered evaluation block. A shared segment is reported, not refused. No pixels |
| Frame store §1.6 | Round trip under `<root>/<sha[:2]>/<sha>.zlib`, with no temporary file left behind, and idempotent. The digest and the declared length are verified on `put`, and the digest again on `get` (a tampered entry fails). The free-space floor refuses and nothing is written. Bad parameters and a relative root are refused. Records carry digests and sizes only |

All extents, corridor values, bin edges, seeds and floors in the tests are labelled test values.

**Residuals.**
1. **Protocol values (AD-27, P-4).** The corridor half-width and range, the bin edges (after D-1/D-2), the
   free-space floor, and the evaluation seed list. The P-4 training, calibration and test seed lists are
   recorded before their first run.
2. **Live data** (D-3 under E8-3a; increment #6): real observer v2 files and recorded frames. The recorder that
   feeds `FrameStore` from verified WP-06 frames belongs to increment #6.
3. **WP-02b**, the lateral-offset target, is needed for real out-of-corridor negatives. The labels already
   handle it.
4. **Declared model limits:** planar geometry (pitch and roll ignored, flat AD-04 road); visibility judged on the
   nearest footprint corner with a pinhole vertical field of view; no occlusion test (one target).
5. **Installed maps and segments** for training (P-2; engineering verification).
6. **The loop10 dataset root** (design §2) is given by the caller and is never defaulted. Its first use is a
   live D-3 activity.

The next step is an independent read-only review of `f095817`, then acceptance and merge. Neither has happened.

## Finding 3: independent review of findings 1 and 2 (2026-10-24 15:33:28)

**Reviewer and method.**
- An independent, read-only reviewer who did not write this increment.
- Read `9e21d31`, `f095817` and `e3a8c37` against base `5f71cde`, and checked them against:
  - thesis `design/wp09-training-pipeline.md` §1–§3 and §8–§9;
  - `decisions.md` "WP-09 training pipeline" (288), "WP-02b scope" (290) and §H P-2 (239) and P-4;
  - `implementation-plan.md` P-2 (163);
  - compat `scenario.py` at `82ee37c` (`target.adjacentLane`).
- Commands (`/dev/shm/compat-p6-venv/bin/python -I`, rc.1 profiles):
  - the three new test files: 56 passed;
  - the whole suite: 227 passed;
  - `check_topology.py`: exit 0.
- In-memory geometry and manifest probes. Nothing in the worktree changed except this entry. No CARLA, no live
  run.

### Verdict: **PASS WITH NOTES. Nothing blocks the merge.**

This increment produces no data: live labelling is increment #6. MEDIUM-1 to MEDIUM-4 must be repaired or
decided before increment #6 records or labels any frame. The merge still awaits acceptance.

### Confirmed
- **Distance.**
  - The ego front is `ego.locationM.x + ego.extentM.x`.
  - The target footprint is centred at `origin + locationM.x·f_t + locationM.y·r_t` with half-sizes `extentM`
    and its own yaw. CARLA's frame is used: forward `(cos ψ, sin ψ)`, right `(−sin ψ, cos ψ)`.
  - The gap is the minimum corner `x` minus the ego front.
  - Probe: an aligned target 30 m ahead gives 25.5 m (WP-02 R-2), and an ego box offset of 0.3 m gives 25.2 m.
    Both offsets are used.
- **Corridor.** A separating-axis test of two rectangles, with two edge normals each and touching counting as
  intersecting, against `[x_front, x_front + maxRange] × [±halfWidth]`.
- **Provenance.** Each label records `observerSha256`, the 1-based `observerLine`, `labelCodeSha256` (the
  SHA-256 of `labels.py`) and `labelParamsDigest`, with `rawSha256` as the join key. There are no bytes.
- **Offline only.** The AST scan of every module outside `assured_aeb/perception/` and `tests/` finds no import
  of the label code (test_perception_labels.py 182). The observer header must be the evaluation-only v2
  schema.
- **Manifest.**
  - It splits by run.
  - It refuses spawn point 1, an evaluation seed, a seed in two splits, a frame digest in two runs, duplicate
    runs and malformed members.
  - A shared segment is reported, as the design states.
  - The identity is the SHA-256 of canonical JSON with no NaN.
- **Frame store.**
  - The digest and the declared length are verified on `put`, and the digest again on `get`.
  - The write is atomic: `mkstemp` in the shard directory, `fsync`, then `os.replace`, with the temporary file
    removed on error.
  - The free-space floor is checked before writing, and an identical entry is idempotent.
  - Records carry digests and sizes only.
- **No pixels** in labels, manifest or store records.

### Issues (none blocks the merge; repair or decide before increment #6)

**MEDIUM-1: visibility is tested on an arbitrary corner among those tied for nearest.**
- Where: labels.py 175 and 181–186.
- `nearest = min(corners, key=x)` keeps the first of the corners that share the minimum `x`, and visibility is
  judged only at that corner.
- Probe: a target yawed 90° at (5.5, 3.0) has footprint x ∈ [4.6, 6.4] and y ∈ [0.8, 5.2]. Its corner
  (4.6, 0.8) lies inside the corridor and inside the 90° field of view, which spans |y| ≤ 3.1 at that range.
  The code tests the tied corner (4.6, 5.2), which is outside, and returns **`visible: False`, `obstacle:
  False`, at 2.2 m in the corridor**. That is a wrong negative in the close-range regime.
- For WP-02b opposite-direction targets on the left lane, the tie also falls on the outer corner, so the
  `visible` field, and with it the measured corridor/visibility disagreement, depends on corner order.
- Repair: define visibility as the footprint (or its in-corridor part) intersecting the horizontal
  field-of-view wedge, plus the vertical test at that point's range. If a single point is kept, use the
  footprint point nearest to the camera axis among the minimum-range points, never an index-ordered tie.
  Add the probe as a test.

**MEDIUM-2: the "WP-02b scope" refusal is not implemented, and cannot be with the manifest's current
inputs.**
- `decisions.md` 290 says that "the WP-09 dataset manifest refuses [adjacent-lane targets] in any evaluation
  run". But `check_manifest`:
  - never reads the scenario: `scenarioSha256` is only format-checked as 64 hex characters and is not verified
    against any scenario content;
  - has no notion of an evaluation run, because evaluation runs (spawn point 1 or evaluation seeds) are
    refused from the manifest altogether.
- So an adjacent-lane target can never be *in* an evaluation run that the manifest sees. The rule "no
  adjacent-lane target in the AD-04 evaluation family" therefore has to be enforced where evaluation runs are
  admitted: the Phase 8 run command and scenario selection (WP-10 #5 or WP-16). That needs a decision that
  names the enforcement point.
- Within WP-09, the manifest should verify each `scenarioSha256` against supplied scenario records and record
  the run's target placement (`inLane` or `adjacentLane{side, direction}`), so the data card and the
  negatives are traceable.
- Record this as a residual, and raise it for an amendment of the decision row.

**MEDIUM-3: the evaluation *segment* is not refused, only spawn point 1.**
- Where: manifest.py 51–53 and 72–75.
- `decisions.md` §H P-2 says "training and calibration use other **segments**", and `implementation-plan.md`
  P-2 says "no evaluation-segment frame enters training".
- The manifest's `evaluation` block holds only `spawnPoint` and `seeds`. Probe: a training run with spawn point
  2 and `segment: "town10-sp1-straight"` gives no refusal and no report.
- Design §3 says only "refuses any run with spawn point 1", so the design and the decision disagree.
- Add the evaluation segment to the `evaluation` block and refuse runs in it. Alternatively, record a decision
  that other spawn points on the evaluation segment are acceptable.

**MEDIUM-4: the dataset identity does not bind the labels.**
- The manifest digest covers `labelParamsDigest`, the runs and the frame digests, but not `labelCodeSha256`
  and no digest of the label records (probe: neither is in the manifest).
- The same dataset identity can therefore stand for different labels, for example after a change to
  `labels.py` with the same parameters.
- The frozen model digest (WP-09) needs a dataset identity that fixes images *and* labels. Add
  `labelCodeSha256` and a per-run labels digest, the SHA-256 of the canonical label list, to the manifest.

**LOW-1: `target_declared` is a free caller flag.** `label_run(…, target_declared=…)` decides positives against
negatives. It should come from the verified scenario record (see MEDIUM-2), not be asserted by the caller.

**LOW-2: frame-store durability details.**
- `os.replace` is not followed by an `fsync` of the shard directory, so after a crash the rename may not be
  durable.
- A crash between `mkstemp` and `os.replace` leaves `.tmp-*.zlib` files that nothing cleans up.
- The free-space check and the write are not atomic with respect to other writers. That is acceptable for one
  writer.
- State these in residual 6, or fsync the directory and sweep the `.tmp-*` files on open.

### Residuals 1 to 6
- Residuals 1 to 6 are accurate.
- Missing: MEDIUM-1 (the visibility tie), MEDIUM-2 (the WP-02b enforcement point and unverified scenario
  digests), MEDIUM-3 (the evaluation segment) and MEDIUM-4 (labels not bound into the identity).

### Recommendation
- Repair MEDIUM-1 and MEDIUM-4.
- Decide MEDIUM-2 (the enforcement point; scenario verification in the manifest) and MEDIUM-3 (the evaluation
  segment) on the thesis side.
- Do all of this before increment #6.
- Record LOW-1 and LOW-2.
- Then acceptance and merge.

## Finding 4: disposition of finding 3 and the repair plan (recorded at 15:36:27, before any change)

**Authority.** The coordinator's disposition of finding 3, under the author's delegation of 2026-10-24, and the
thesis row `decisions.md` "WP-09 data separation" (15:34). Design `wp09-training-pipeline.md` §3 is aligned to it (by
segment; placement recorded; labels bound into the identity). This finding is engineering evidence only and does not
accept or merge anything.

**Planned repairs on this branch.**
1. **MEDIUM-1 (visibility tie).**
   - Visibility comes from the **intersection of the target footprint with the horizontal field-of-view wedge**, and
     no longer from one corner chosen by its index among tied corners.
     - The footprint is clipped, in the camera-relative ego frame, by the wedge's two half-planes
       `tan(h)·dx ∓ dy ≥ 0` (convex clipping; touching counts, as for the corridor).
     - It is horizontally visible when the clipped region is non-empty and reaches `dx > 0`.
   - The vertical test applies at the clipped region's **largest range**. The box is a vertical prism, and the
     pinhole vertical aperture widens with range, so some part of the target is in the vertical field of view if and
     only if that part is in view at the largest range.
   - `obstacle` stays `inCorridor and visible` (design §3).
     - A stricter form would test visibility only on the in-corridor part of the footprint. It is recorded as a
       residual, and is not adopted here: neither the decision nor the disposition asks for it.
   - The reviewer's probe becomes a test: a target yawed 90° at (5.5, 3.0) is labelled visible, an obstacle, at
     2.2 m.
2. **MEDIUM-2 and LOW-1 (scenario and placement).**
   - A new offline module, `perception/scenario.py`, reads a live-scenario file's bytes and verifies its SHA-256
     against the declared `scenarioSha256`.
   - It derives the **target placement**:
     - `none` (schema 1, or schema 2 without a target);
     - `ego-lane`;
     - `adjacent-lane` with `side` and `direction`.
   - It mirrors the placement members of compat `xverse_compat_carla/scenario.py` `target_of` (schemas 1 and 2;
     `adjacentLane` exactly `{side, direction}`), and refuses an unknown schema or value.
   - It does not re-run compat's full validation, which stays at spawn. Blueprints keep no import of compat.
   - Two consumers use it:
     - `label_run` takes the verified scenario (bytes plus digest) instead of the caller flag `target_declared`;
     - `check_manifest` takes a required mapping from run identifier to scenario file. It refuses a missing file, a
       digest mismatch, a recorded `targetPlacement` that differs from the derived one, and a scenario whose
       `spawnPointIndex` or `map` differs from the run's.
   - **Not repaired here (obligation recorded).** Refusing adjacent-lane targets in evaluation runs belongs to
     WP-10 #5 (run command) and WP-16 (scenario selection), as the decision row (1) says. The manifest contains no
     evaluation run.
3. **MEDIUM-3 (evaluation segment).**
   - Each run's `segment` becomes a record `{map, roadId, sectionId}`: the OpenDRIVE road and lane section of its
     spawn waypoint, read from the live run (increment #6).
   - The manifest's `evaluation` block gains the declared `segment` of spawn point 1, a parameter with no default
     (P-2 map verification; `TODO: engineering verification`).
   - Any **training or calibration** run on that segment is refused, whatever its spawn point.
   - A test-split run on it is reported, not refused, because the decision names training and calibration only.
   - Tests cover spawn point 2 on the evaluation segment (refused for training and for calibration).
4. **MEDIUM-4 (identity binds the labels).**
   - The manifest gains the top-level `labelCodeSha256` and a per-run `labelsSha256`: the SHA-256 of the canonical
     label list, from a new `labels.labels_digest`.
   - Because every label's provenance carries `labelCodeSha256`, a label-code change changes every
     `labelsSha256`, and with them the identity.
   - A test shows that a label-code change changes the identity.
5. **LOW-2 (store durability).**
   - After `os.replace`, the shard directory is fsynced.
   - On open, the store removes stale `.tmp-*.zlib` files left by an interrupted write. It does this for a single
     writer, at open time only.
   - A test covers both: the directory fsync is observed, and stale temporary files are swept.
6. Run the tests and the checker, record finding 5, and commit.

## Finding 5: repair result (2026-10-24 15:41:12)

**What changed, per finding 4.**

1. **MEDIUM-1 (`labels.py`).**
   - `geometry` clips the camera-relative footprint with the two half-planes of the horizontal wedge, using the new
     `clip_half_plane` (Sutherland–Hodgman; boundary points kept).
   - It applies the vertical test at the clipped region's largest range. No corner is selected any more, and the
     distance uses only the minimum range.
   - Tests:
     - the reviewer's probe (yawed 90° at (5.5, 3.0)) gives distance 2.2 m, in the corridor, visible, an obstacle,
       `bin-0`;
     - its mirror image on the other side gives the same result;
     - a footprint wholly outside the wedge is not visible;
     - the boundary and outside behaviour of the clipping.
   - **Regression check:** the pre-repair `labels.py` (`HEAD` `7456784`, run from a scratch copy) returns
     `visible: False` for the probe, which reproduces the defect.
2. **MEDIUM-2 and LOW-1 (new `perception/scenario.py`; `labels.py`; `manifest.py`).**
   - `verified_scenario(bytes, sha256)` verifies the digest first. It then derives `spawnPointIndex`, `map` and
     `targetPlacement` (`none`, `ego-lane`, `adjacent-lane{side, direction}`).
   - `label_run` now takes `scenario=` and `scenario_sha256=`. The caller flag `target_declared` is gone: passing it
     raises `TypeError`, which a test shows.
   - `check_manifest(manifest, scenarios)` takes a **required** mapping from run identifier to scenario file. It
     refuses:
     - a missing file;
     - a digest mismatch;
     - a recorded placement that differs from the derived one;
     - a malformed placement;
     - a spawn-point or map mismatch;
     - a schema-1 scenario with no map.
   - The manifest records no host path (a test checks this).
3. **MEDIUM-3 (`manifest.py`).**
   - The schema is now `assured-aeb.dataset-manifest/2`.
   - A run's `segment` is `{map, roadId, sectionId}`, and `evaluation.segment` is a required declared parameter.
   - Training and calibration runs on the evaluation segment are refused whatever their spawn point. Tests: spawn
     point 2 on it, for training and for calibration.
   - A test-split run on it is reported.
   - Another lane section of the same road is admitted.
4. **MEDIUM-4.**
   - `labels.labels_digest` gives the SHA-256 of the canonical label list.
   - The manifest binds the top-level `labelCodeSha256` and a per-run `labelsSha256`, both refused unless they are
     SHA-256 hex.
   - Test: changing `LABEL_CODE_SHA256` changes the run's labels digest and the dataset identity.
5. **LOW-2 (`store.py`).**
   - After `os.replace`, the shard directory is fsynced (a test observes the call).
   - On open, the store removes `.tmp-*.zlib` files in the two-hex shard directories only, then fsyncs each shard it
     touched. It counts them in `swept`.
   - A test shows that the stale file is removed, while other names and non-shard directories are kept.
   - The single-writer assumption is stated in the module docstring.

**Commands** (`/dev/shm/compat-p6-venv/bin/python -I`, rc.1 profiles):
- the three perception test files: 87 passed (56 before);
- the whole suite: 258 passed (227 before);
- `check_topology.py`: exit 0;
- `__pycache__` removed before the commit.

**Residuals (updating finding 2's list).**
- Residual 4: "visibility judged on the nearest corner" is **closed** by MEDIUM-1.
  - What remains is the planar, flat-road model, and the vertical prism, now stated.
  - **New option, not adopted:** test visibility only on the in-corridor part of the footprint. It is stricter for
    targets that are partly in the corridor at close range. It would need a decision if wanted.
- **New residual 7, `TODO: engineering verification`.** The value of `evaluation.segment`: the OpenDRIVE road and
  lane section of Town10HD_Opt spawn point 1 (P-2 map verification).
  - Each run's `segment` must also be read from the live spawn waypoint (`road_id`, `section_id`) by the increment
    #6 recorder. It is never typed by hand.
- **New residual 8, an obligation outside this repository's WP-09 scope.** Refusing evaluation runs whose scenario
  declares `adjacentLane` belongs to WP-10 #5 (the run command) and WP-16 (scenario selection), per decisions.md "WP-09
  data separation" (1). It is not implemented here.
- **Residual 9.** `scenario.py` mirrors only the placement members of compat `target_of`. Compat's full validation
  stays at spawn. If compat's live-scenario schema changes, this mirror must change too: an unknown schema is refused.
- Residuals 1, 2, 3, 5 and 6 are unchanged.

**Status.** These are repairs on the candidate only. Acceptance and the merge are still pending.

## Finding 6: independent review of findings 4 and 5 (2026-10-24 16:01:28)

**Reviewer and method.**
- An independent, read-only reviewer who wrote neither the increment nor its repairs.
- Read `7456784` (finding 4) and `8f5a042` (repairs, finding 5) against `1b71480`, and checked them against:
  - thesis `decisions.md` rows "WP-09 training pipeline" (288), "WP-02b scope" (290) and "WP-09 data separation"
    (291), and `implementation-plan.md` P-2 (163) and K-9 (44);
  - `design/wp09-training-pipeline.md` §3 and its alignment note of 15:34;
  - compat main `34b514d`, read-only: `xverse_compat_carla/scenario.py` `target_of`, `_transform` and
    `CAMERA_MOUNT`, and `xdl/descriptors/aeb-sim/carla-sensors.json` (camera 800 × 600 at 90°).
- Thesis repository: branch `agent/synchronize-thesis-obsidian-notes`, HEAD `d97fdd1` equal to its upstream after
  `git fetch --prune`, with no incoming change to the canonical note.
- Commands (`/dev/shm/compat-p6-venv/bin/python -I`; rc.1 profiles from a scratch `git archive` export of
  `xverse-lite-v1.0.0-rc.1` = `64ff9d3eb`):
  - the whole suite, `-p no:cacheprovider`: **258 passed**;
  - `check_topology.py --platform-profiles <export>/xdl/profiles`: exit 0, 50 checks, all PASS;
  - `__pycache__` removed afterwards. The worktree is clean except for this entry.
- Probes, run from scratch scripts with no bytecode written:
  - a brute-force visibility oracle over 4 000 random targets (position, yaw, extents, offsets and heights);
  - edge cases;
  - the pre-repair `labels.py` from `7456784`;
  - a second `FrameStore` opened during a `put`.
- No CARLA, no live run, no download. The loop10 dataset and soak paths were not touched.

### Verdict: **PASS WITH NOTES. Nothing blocks the merge of increment #1.**

The dispositions of finding 3 are implemented as planned in finding 4. MEDIUM-1 below must be repaired or decided on
the thesis side before increment #6 records any frame, like the MEDIUM items of finding 3. The LOW items can be
repaired or recorded as residuals. The merge still awaits acceptance.

### Dispositions of finding 3, verified
- **MEDIUM-1 (visibility): closed.**
  - The wedge is the intersection of `tan(h)·dx − dy ≥ 0` and `tan(h)·dx + dy ≥ 0`, that is `|dy| ≤ tan(h)·dx`, which
    implies `dx ≥ 0` because `0 < fov < 180` is enforced.
  - `clip_half_plane` is a correct Sutherland–Hodgman step for a convex polygon. Its denominator cannot be zero on
    either crossing branch.
  - The vertical test at the clipped region's largest depth is exact for the pinhole model:
    - the aperture `|dz| ≤ dx·tan(v)` grows with depth;
    - the horizontal and vertical conditions are independent for a vertical prism;
    - `tan(v) = tan(h)·height/width` holds for square pixels;
    - the camera is mounted with zero rotation (compat `_transform`).
  - **Probes:**
    - The oracle agrees with `geometry` in all 4 000 random cases.
    - Edge cases agree with it:
      - a target straddling the camera plane beside the ego, outside the wedge and partly inside it;
      - a target wholly behind the camera;
      - a corner exactly on the wedge edge;
      - a footprint touching the wedge apex;
      - a target 50 m above;
      - an ego yawed 30°.
    - The reviewer's probe (yawed 90° at (5.5, 3.0)) gives 2.2 m, in the corridor and visible. The pre-repair
      `labels.py` of `7456784` gives `visible: False`, which confirms the regression check of finding 5.
- **MEDIUM-2 and LOW-1 (scenario and placement): closed within WP-09.**
  - `verified_scenario` checks the SHA-256 before it parses anything.
  - Its placement members mirror compat `target_of`. It is looser on the other members, as residual 9 declares.
  - `target_declared` is gone.
  - `check_manifest` requires the mapping and refuses each of these cases:
    - a missing file;
    - a digest mismatch;
    - a placement mismatch or a malformed placement;
    - a spawn-point mismatch;
    - a map mismatch.
  - The evaluation-run refusal is recorded as an obligation of WP-10 #5 and WP-16 in residual 8 and in both module
    docstrings, as row 291 (1) says.
- **MEDIUM-3 (evaluation segment): implemented as decided, with a gap; see MEDIUM-1 below.**
  - The schema is `/2`, and the segment is `{map, roadId, sectionId}` with integer ids.
  - `evaluation.segment` is required, has no default and is a marked test value in the tests.
  - Training and calibration on it are refused whatever the spawn point.
  - A test-split run on it is reported. Spawn point 1 is still refused for every split.
- **MEDIUM-4 (identity): implemented.**
  - `labelCodeSha256` (top level) and `labelsSha256` (per run) are in the canonical manifest, so they enter the
    identity.
  - "Label code" is the SHA-256 of the bytes of `labels.py` alone; see LOW-2.
  - The test monkeypatches `LABEL_CODE_SHA256`. It shows that the constant flows into the labels digest and the
    identity. It does not show which code is hashed.
- **LOW-2 (store durability): implemented, with one gap and one side effect; see LOW-4.**
  - The shard directory is fsynced after `os.replace`.
  - The sweep stays inside the store:
    - it visits only two-hex, non-symlink subdirectories of the root;
    - it removes only regular, non-symlink `.tmp-*.zlib` files;
    - a stored entry `<sha>.zlib` can never match.
- **No invented protocol value.**
  - The modules hold no numeric protocol value. `EVALUATION_SPAWN_POINT = 1` is sourced (P-2, K-9), and the camera
    values equal compat `CAMERA_MOUNT` and the descriptor.
  - The store's floor, compression level and frame length are required arguments.
- **No pixels.**
  - Labels, the manifest and store records carry digests, sizes and geometry only.
  - `FrameStore.get` returns bytes in process only, and no host path enters the manifest.

### Issues

**MEDIUM-1: P-2 by segment is judged only at the spawn waypoint.**
- **What the rule requires.**
  - Row 291 (2) refuses "any training or calibration run on the evaluation road segment".
  - `implementation-plan.md` P-2 adds: "No evaluation-segment frame enters training".
- **What the code checks.** A run's `segment` is the road and lane section of its *spawn* waypoint (finding 4
  item 3), and `evaluation.segment` is a single `{map, roadId, sectionId}`.
- **Two cases the rule misses:**
  - A training run spawned in an upstream section that drives into the evaluation section, or whose target is
    placed there, passes. Its frames show the evaluation segment.
  - If the evaluation lane ahead of spawn point 1 (about 120 m, K-9) spans more than one OpenDRIVE lane section,
    only its first section is protected.
- **Repair, or a thesis-side decision, before increment #6:**
  - record per run the set of `{road, section}` traversed by the ego, and occupied by the target, over the recorded
    frames, read from the live waypoints by the increment #6 recorder;
  - declare the evaluation segment as the set of sections that the evaluation trajectory covers
    (`TODO: engineering verification`);
  - refuse any intersection for training and calibration.

  Alternatively, record a decision that spawn-section equality is sufficient, with the limit stated in the data
  card.

**LOW-1: the label binding in the manifest is declarative.**
- `check_manifest` only checks that four members are 64-hex: `labelsSha256`, `labelCodeSha256`, `labelParamsDigest`
  and `observerSha256`. It verifies none of them.
- It does not recompute `labelsSha256` from a run's label records.
- It does not check that each label's provenance (`labelCodeSha256`, `labelParamsDigest`, `observerSha256`) equals
  the manifest's.
- It does not check that the labelled `rawSha256` set is contained in the run's `frames`.
- The MEDIUM-4 test therefore holds only when the producer computes these digests correctly. Finding 3 MEDIUM-2
  raised the same pattern for `scenarioSha256`.
- Repair: add a verifier that takes each run's label list, as `scenarios` now does, or record it as an obligation
  of increment #6.

**LOW-2: the label-code hash covers `labels.py` only.**
- `label_run` depends on `scenario.verified_scenario`: the placement kind decides whether a target is declared.
  `scenario.py` is not in `LABEL_CODE_SHA256`.
- The identity is not weakened, because `labelsSha256` binds the label content. The provenance member
  `labelCodeSha256` does not, however, identify the whole label code.
- Repair: hash the label-code closure (`labels.py` and `scenario.py`, named and ordered), or state the limit.

**LOW-3: the map comparison binds declared strings only.**
- Compat checks only that the scenario's `map` is a non-empty string. Nothing in compat `src/` compares it with the
  loaded world. Only the observer header records `world.get_map().name` (`observe.py` 89, 181).
- `check_manifest` compares the scenario's `map` with the run segment's `map`, and both are declared.
- A schema-1 file with a stray `map` member also passes, because `verified_scenario` returns it.
- Increment #6 should:
  - take the map from the evaluation-only observer header, that is from the actual world;
  - state how CARLA's reported name is compared with the scenario's `Town10HD_Opt` (`TODO: engineering
    verification`);
  - refuse a schema-1 `map`.

**LOW-4: the sweep runs on every open, and a new shard directory is not made durable.**
- **The sweep.** The single-writer assumption is documented but not enforced.
  - Any `FrameStore` opened while the recorder writes deletes the writer's in-flight temporary file. This includes
    an opener that only reads, such as a later loader.
  - Probe: a second open during `put` makes the writer's `os.replace` fail with `FileNotFoundError`.
  - Nothing is left behind, nothing outside the shard directories is touched, and nothing is corrupted. The failure
    is loud.
  - The sweep also scans every shard on each open.
- **Durability.** After `mkdir` of a new shard, the root directory is not fsynced, so the new shard entry may not
  survive a crash.
- **Repair options:**
  - an advisory lock (`fcntl.flock` on a lock file in the root), held by the writer, with the sweep done only under
    it, or a separate writer mode;
  - an fsync of the root after creating a shard.

**LOW-5 (editorial): some test fixture values are not marked.**
- `test_perception_labels.py` marks only its extents, corridor and bin edges as test values.
- Its scenario fixture, and that of `test_perception_manifest.py`, also hold unmarked values: `spawnPointIndex` 7
  and 3, `distanceAheadM` 30.0, and `egoBlueprint` `vehicle.test`.
- Mark them as test values.

**Note (no issue).** The distance is the minimum over the *whole* footprint, not over its in-corridor part. It
belongs with the in-corridor visibility option of finding 5 residual 4, and is for one AD-27 decision.

### Residuals
- Residuals 7 to 9 of finding 5 are accurate.
- Add MEDIUM-1 (the segment traversal and the multi-section evaluation segment) and LOW-1 to LOW-4.

### Recommendation
- Before increment #6: decide or repair MEDIUM-1 on the thesis side (row 291 (2)), and repair LOW-1 or record it as
  an increment #6 obligation.
- Repair LOW-2 to LOW-5 or record them.
- Then acceptance and the merge of increment #1. Neither has happened.

## Finding 7: disposition of finding 6 and the repair plan (recorded at 2026-10-24 16:07:10, before any change)

**Source of the dispositions.** Thesis `specs/002-assured-aeb/decisions.md` (working copy, blob `3c051132`): the row
"WP-09 data separation, amendment 1" (16:02; under the author's delegation). It amends (2) of "WP-09 data
separation". Also `design/wp09-training-pipeline.md` "Alignment 2, 16:02". Thesis HEAD is `d97fdd1`, equal to its
upstream after `git fetch --prune`, with no incoming change to the canonical note. These dispositions are the
coordinator's relay of those rows. They are not an approval of the merge.

1. **MEDIUM-1: repaired as amended (2).**
   - **Schema.** The manifest becomes `assured-aeb.dataset-manifest/3`.
   - **Evaluation set.** `evaluation.segment` (one `{map, roadId, sectionId}`) is replaced by
     `evaluation.segmentSections`, a declared **set** of lane sections:
     - a non-empty list of `{map, roadId, sectionId}` with integer ids;
     - unique and in canonical order (sorted by `(map, roadId, sectionId)`), so that one set has one identity;
     - required by `build_manifest`, with no default;
     - its value is `TODO: engineering verification` on Town10HD_Opt (residual 7, updated), and the tests use
       marked test values.
   - **Traversed set per run.** The run member `segment` (the spawn waypoint's section) is replaced by
     `traversedSections`: the set of lane sections the ego actually traversed. It has the same form (non-empty,
     unique, canonical order) and is required. Increment #6's recorder fills it from the ego waypoint of every recorded
     frame (an obligation of #6). The spawn section is a member of that set, so nothing the old member carried is lost.
     The map check against the verified scenario now applies to every traversed section.
   - **Refusal.** A training or calibration run whose `traversedSections` meets `evaluation.segmentSections` is
     refused **as a whole**, whatever its spawn point, with the intersecting sections named. A test-split run that
     meets it is reported, not refused, as before. The shared-section report becomes per section.
   - **Scope as decided.** The decided set is the **ego's** traversed sections. Finding 6 also proposed the sections
     the target occupies; the row does not adopt that, so it is not implemented. This is recorded as a new residual 10
     for a later decision; it is not a defect of this repair. Whether the traversed set is complete, that is one entry
     per recorded frame, cannot be checked by the manifest. It is an obligation of #6.
2. **LOW-1: repaired.** `check_manifest(manifest, scenarios, labels)` takes a third **required** mapping from
   `runId` to that run's label records (no default; a missing run is refused). For each run it refuses:
   - `labels_digest(records) != labelsSha256`;
   - any label whose `provenance.labelCodeSha256` or `provenance.labelParamsDigest` differs from the manifest's,
     or whose `provenance.observerSha256` differs from the run's;
   - a labelled `(frame, rawSha256)` pair that is not among the run's `frames`, or a frame labelled twice.

   It also refuses a manifest whose `labelCodeSha256` is not the running label code's `LABEL_CODE_SHA256`: the
   identity must name the code that checks it. Verifying `labelParamsDigest` against a parameter record, and
   `observerSha256` against the observer file's bytes, needs those artefacts. Both are left to #6, which holds
   them (residual 11).
3. **LOW-2: repaired.** `LABEL_CODE_SHA256` becomes the SHA-256 of the canonical list `[{file, sha256}]` over the
   named, ordered closure `("labels.py", "scenario.py")`. It is computed by a function `label_code_digest(directory)`,
   so a test can show that a change to `scenario.py` alone changes it.
4. **LOW-4: repaired as decided.**
   - **Sweep.** `FrameStore` takes a required keyword `writable` (a bool, no default). Only a writable open sweeps
     stale temporary files. A read-only open never sweeps, and its `put` is refused.
   - **Durability.** When `put` creates a new shard directory, it fsyncs the root after the `mkdir` and before
     writing.
   - **Limit kept.** Two concurrent *writable* opens are still not excluded. An advisory lock was not decided. This
     single-writer limit stays declared in the docstring (residual 12).
5. **LOW-5: repaired.** The fixture values of `test_perception_labels.py` and `test_perception_manifest.py` become
   named constants marked as test values:
   - spawn points 7 and 3;
   - `distanceAheadM` 30.0;
   - the blueprint `vehicle.test`;
   - the target `hold`;
   - the run seeds and road and section ids.
6. **LOW-3: recorded as an obligation of increment #6, not repaired here.** Increment #6 binds the map to the
   evaluation-only observer header's loaded-world map (`world.get_map().name`). It states how CARLA's reported name
   is compared with `Town10HD_Opt` (`TODO: engineering verification`) and refuses a schema-1 scenario's `map`. The
   obligation is added to `scenario.py`'s and `manifest.py`'s docstrings and to the residual list.
7. **Tests to add.** For each repair, positive and negative cases:
   - MEDIUM-1:
     - an upstream-spawned training run that traverses an evaluation section is refused;
     - a multi-section evaluation set protects its second section;
     - a test split is reported, not refused;
     - disjoint sets are admitted;
     - malformed, duplicate or unordered sets are refused;
     - a `traversedSections` map that differs from the scenario map is refused.
   - LOW-1: each digest mismatch, a foreign frame, a duplicate label and a missing label list are refused, with a
     real `label_run` output as the positive case.
   - LOW-2: a change to `scenario.py` alone changes the digest.
   - LOW-4:
     - a read-only open does not sweep and refuses `put`;
     - a read-only open during a writer's `put` leaves the writer's rename intact (the finding 6 probe);
     - the root is fsynced on the first shard creation only.

   Then the whole suite with the rc.1 profiles and `check_topology.py`, followed by finding 8.
8. **Out of scope.** No CARLA, live run or download. The loop10 dataset and soak paths are not touched. The thesis
   repository is read-only, and no thesis record is edited.

## Finding 8: Codex inspection of unfinished amendment-1 repair, and completion design (2026-10-24)

The candidate was inherited at `c992ac7` with five modified files: `labels.py`, `manifest.py`, `scenario.py`,
`store.py` and `tests/test_perception_store.py`. They were not discarded or stashed. Before any Codex repair, their
complete diff and individual SHA-256 hashes were preserved under
`docs/evidence/wp09-claude-dirty-before-codex-20261024/` (`original.patch`, SHA-256
`0e75f85d6ab5101a7eb4a91934627e26c5a977c87c74fedfd0ad4ccce1787eff`; `original-state.json`).
This review/design finding is committed separately before further code changes.

**Read-only findings.**
- The pending source implements the amendment-1 section sets and whole-run intersection refusal; it checks actual
  label lists against run digests/provenance, hashes both label source files, and confines sweeping to writable opens
  with a root fsync after creating a shard. These are consistent with finding 7's decided design.
- Manifest tests still use the old evaluation-segment object, `segment` run field, two-argument `check_manifest`,
  arbitrary label-code hashes and placeholder label digests. They cannot verify the new interface and need migration.
  The promised section-set and actual label-binding negative tests have not been added.
- The label/manifest scenario fixtures still contain unnamed test values (LOW-5); the source-closure sensitivity
  test is missing. The newly added store tests already express the writable/read-only and fsync obligations.
- `check_manifest` does not validate a run id before using it as a set/dictionary key, and a malformed unhashable
  split can proceed after a refusal to a set operation. The new label-verification path needs typed frame tables
  before constructing its held pairs. Also, duplicate-label detection uses `(frame, rawSha256)`, so two different
  byte digests under the same frame number can evade the promised "frame labelled twice" refusal.
- LOW-3 is correctly still an obligation of recorder increment #6: actual observer-header map binding, CARLA map-name
  comparison and schema-1 stray-map refusal remain unimplemented here. Do not claim those are closed.

**Completion design, before code.** Preserve and finish finding 7's source changes. Migrate the tests to schema /3
and the required label-record mapping; generate positive manifests with real `label_run` output, unique per-run raw
frame digests and matching observer/parameter/code provenance. Preserve the existing scenario and split negative
coverage, add the planned section-set/intersection and label-binding tests, name the existing test-only fixture values,
and demonstrate that changing `scenario.py` alone changes the closure digest.

Add small fail-closed guards for non-string/empty run ids, invalid split types, integer frame/time members and duplicate
frame ids before their hash/set use. Track labelled frame numbers independently of digests, so the same CARLA frame
cannot be labelled twice. These guards implement the existing malformed-member and LOW-1 duplicate-label requirements;
they introduce no physical bound or protocol value. Observer-map binding and single-writer limits remain as decided.

No pytest or heavy work is run while the coordinator's full platform regression is active. Only syntax and small
stdlib fixture probes are permitted now; the full owning suite and independent re-review remain pending before
acceptance or merge. No CARLA, inference runtime, download, live data, dataset-root or soak-path operation is authorized
by this completion.

## Finding 9: amendment-1 completion result (2026-10-24; full suite and independent re-review pending)

Completed the inherited five-file repair after the source-preserving review/design commit `eb6ed59`:
- retained Claude's schema `/3`, per-run `traversedSections`, whole-run evaluation-section refusal, actual label-list
  verification, two-file label-code closure and writable-only sweep/root-fsync changes;
- migrated every manifest test to the required scenario and label mappings and canonical section sets. Positive
  fixtures now use actual `label_run` results with matching observer bytes, label parameter/code digests and distinct
  per-run frame bytes. They no longer pass placeholder label identities;
- added the decided upstream-spawn/second-protected-section, canonical/malformed set, actual label-digest/provenance,
  foreign/duplicate frame, missing-label and scenario-only code-change cases;
- completed malformed run-id/split/frame-table guards before hash/set use and unique labelled-frame detection;
- marked the existing scenario fixture spawn, target distance, hold and test blueprint settings explicitly as
  test-only values. Camera configuration remains sourced, and no protocol value was selected.

**Bounded checks actually performed now.** A small direct fixture probe, without a pytest runner, passed **36 checks**
in about 0.3 s. It covered the actual-label positive manifest, protected-section crossing and test-split reporting,
canonical/malformed section sets, all provenance bindings, missing/different label records, foreign/duplicate frames,
malformed hash-key members, scenario-only source sensitivity, read-only sweep refusal, read-only versus writable
second-open behaviour during a put, and first-shard root fsync versus existing-shard fsync. All seven changed Python
files compile in memory; `git diff --check` passes. The first probe invocation used a wrong relative edit path and was
corrected before the successful complete direct check; it was not a product failure. No CARLA, inference runtime,
pytest runner, download, live dataset or soak path was used.

The original five-file dirty-state snapshot remains at
`docs/evidence/wp09-claude-dirty-before-codex-20261024/`. Its patch still hashes to
`0e75f85d6ab5101a7eb4a91934627e26c5a977c87c74fedfd0ad4ccce1787eff`; it can be reconstructed against the recorded
`c992ac7` base. No original edit was stashed, discarded or silently replaced.

**Required next full-suite command, only after the coordinator's platform regression has finished:** from
`automotive/assured-aeb`, run:

```sh
env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  XVERSE_PLATFORM_PROFILES=/tmp/codex-xverse-review-20261024-q93eotxv/xdl/profiles \
  /dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider tests --tb=short
```

Then independently re-review the complete source/test repair and later verify its assembly with current main.
The full suite has **not** been run on this repair, and no acceptance or merge is claimed.

**Unchanged residuals from finding 7.** Recorder #6 must supply every recorded ego section and bind the declared map
and observer digest to actual observer-header/world bytes; map-name comparison and schema-1 stray-map refusal remain
its explicit LOW-3 obligations. Verification of the label parameter digest against its source record and observer
bytes also belongs to #6. Actual map sections and dataset parameters remain TODO. Target-occupied sections and multiple
writable opens remain the declared scope/ single-writer limits, not repaired capabilities. Existing planar geometry,
visibility and offline-only evidence limits continue to apply. No principal-data or scientific claim follows.

## Finding 10: independent parent completion review, PASS WITH NOTES; full suite pending (2026-10-24)

Reviewed candidate `40d80ccc9d13da60b20bcda76c77406cc1cf5a7a` against the preserved pre-Codex patch,
findings 7 to 9 and the delegated data-separation amendment. The parent did not author the completion repair.
The original dirty-state snapshot is retained; no source history or intended change was discarded.

The complete manifest/schema-/3 delta, label-code closure, scenario boundary, writable/read-only store changes
and migrated tests match the recorded scope. The admitted set is based on every recorded ego-traversed section,
not the spawn section alone. Actual supplied label lists are hashed and checked against their run and source
provenance; duplicate frame numbers are refused independently of byte digests. A reader never sweeps the writer's
temporary file; new shards and stored-frame publication have the recorded directory-fsync steps. Multi-writer
exclusion is not claimed.

Eight tiny public-admission checks independently pass: a positive genuine-label manifest, changed label digest,
foreign/duplicate labels, two-digest duplicate frames, duplicate frame table and the two protected-section
training/calibration cases. `git diff --check` passes. No pytest, simulation or framework import was run while the
platform regression is active. The full source and assembled owning suite remain required before acceptance.

Carried notes are material: recorder #6 must attest traversed-section completeness and observer/map/source-record
binding; the manifest cannot prove those facts from supplied metadata. Hash/provenance checks do not re-execute
label geometry or establish source truth. Training/export must validate the label fields it consumes and preserve
recorded exclusions. Existing planar/visibility and single-writer limits remain; no dataset or principal result
is accepted by this source review. No numeric protocol value was chosen.

## Finding 11: queued full-suite provenance assertion failure; repair design before edit (2026-10-24)

The serialized owning suite on assembled candidate `92dfe5ad4b77f9a4aa8aecfbb116872811a69267` returned **1 failed,
526 passed** in 31.28 s. The coordinator's receipt is thesis
`specs/002-assured-aeb/review/codex-serial-verification-20261024/dataset-labels/receipt.json`.
`test_provenance_and_no_pixels` still expects the SHA-256 of raw `labels.py` alone (`616539fd…d06c20`), whereas the
label correctly carries the named, ordered `labels.py` plus `scenario.py` closure digest (`651a3a66…6c20a5`).
The delegated 16:02 amendment explicitly requires that closure, implemented and reviewed in findings 7–10.
Changing production back to the single-file hash would violate that approved contract.

Repair only the stale test expectation: independently build the canonical `[{file, sha256}]` record for the
explicitly required two filenames, hash it, and compare the emitted provenance against it. Assert the required
closure membership/order as well; do not merely compare the value to the production constant or call the production
hash helper. Keep the observer, parameter, frame and no-pixel assertions. No product, parameter, manifest or original
snapshot change is needed. Run the corrected tiny direct test and syntax/diff checks only; the coordinator retains
the heavy execution slot and must repeat the full owning suite on the new exact revision before acceptance.

## Finding 12: narrow provenance test repair completed; full rerun pending (2026-10-24)

The sole stale expectation now independently hashes the explicitly named two-file source closure and checks its
membership/order. No product file or scientific value changed. The genuine `label_run`-backed
`test_provenance_and_no_pixels` passes when called directly; the changed test module compiles and
`git diff --check` passes. No pytest runner or framework inference/training was run. The previous **526 passed**
result belongs to `92dfe5a`, not this repair; repeat the complete owning suite on the new candidate. Independent
review, acceptance and merge remain outstanding, with all recorder #6 and training-consumer notes preserved.
