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
