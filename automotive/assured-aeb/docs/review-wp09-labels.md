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
