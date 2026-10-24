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
