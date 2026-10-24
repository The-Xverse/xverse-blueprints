# WP-12b review log: isolated interpreter flags for the generated Phase 8 unit commands

Candidate: branch `candidate/phase8-wp12b-unit-flags-20261024`, from blueprints main `18201fe` (fetched first). This
is a direct engineering increment, and the log follows the same order:
1. findings come before repairs;
2. an independent read-only review;
3. acceptance;
4. a merge.

None of the last three has happened yet.

**Inputs.**
- Thesis `specs/002-assured-aeb/decisions.md` (working copy, blob `3c051132`; thesis HEAD `d97fdd1` equals its
  upstream after `git fetch --prune`, with no incoming change to the canonical note):
  - the row "WP-09 #3 unit isolation" (15:39), R-1: every Phase 8 unit command runs its interpreter with `-S -s -B`
    and `PYTHONDONTWRITEBYTECODE=1`;
  - the row "S1e (1.0.x unit isolation) R-D and L-1; WP-12 unit flags" (15:56): `topology.py:588` generates the Phase
    8 unit commands with `-B` only, against R-1; it is repaired as increment WP-12b before WP-13's units are wired.
- The WP-08b U4 command template, compat branch `candidate/phase8-wp08b-isolation-20261024` (`840091a`, not merged),
  `src/xverse_compat/inference/unit.py`: `INTERPRETER_FLAGS = ("-S", "-s", "-B")`; `FIXED_ENVIRONMENT` (four
  settings); `environment(site_packages, extra_paths, home)` returning `PATH`, `HOME`, the fixed settings and
  `PYTHONPATH` = the venv's site-packages, then the extra paths; `command(interpreter, module, *args)`. The pattern is
  mirrored here; nothing is imported from the unmerged branch.
- The Phase 7 blueprint harness, `automotive/thesis-lite-carla-closed-loop/units.py` 66–82 and
  `test_live_closed_loop.py` 186: the run harness supplies the environment **values**; the deployment's process
  payload declares only `environmentNames = sorted(unit.environment)`.
- The platform runtime-compatibility profile v0.2 (rc.1 export of `64ff9d3eb`, `xdl/profiles`), `$defs/process`:
  `executable`, `arguments`, `workingDirectory`, `environmentNames`, `inheritedHandles`, `implicitShell`, optional
  `stop` and `stderr`, with `additionalProperties: false`. The process payload therefore cannot carry values.

## Finding 1: design (2026-10-24 16:00:51, before any code)

1. **The defect.** `topology.py` `deployment()` (lines 588–590) emits, for every unit of every arm and both forms:
   `"arguments": ["-B", "-m", "assured_aeb.units.<unit>"]` and `"environmentNames": ["HOME", "PATH", "PYTHONPATH"]`.
   Without `-S` the interpreter runs `site`: the base interpreter's site-packages, its `.pth` hooks and any editable
   install can fill a module missing from the unit venv. Without `-s` the user site is searched. Neither the flag
   `PYTHONDONTWRITEBYTECODE` nor its name is declared. This holds for all seven units (`carla-adapter` on Python
   3.10; `vehicle-loop`, `front-zone`, `adas-hpc`, `vc-functional`, `vc-assurance` and the 7-unit variant's
   `chassis-brake` on Python 3.13), in the 8 committed `deployment.json` files and in the admission dry-run variant.
2. **Design.**
   - **D-1 Arguments.** Every generated unit command becomes `[executable, "-S", "-s", "-B", "-m",
     "assured_aeb.units.<unit>"]`. The flags are a module constant `INTERPRETER_FLAGS = ("-S", "-s", "-B")`, as in
     the template; `-s` is redundant under `-S` and is kept for parity with the template and R-1.
   - **D-2 Environment values (declared by function, supplied by the harness).** A standard-library function
     `unit_environment(unit, site_packages, *, home, extra_paths=())` returns the complete environment of one unit:
     `PATH=/usr/bin`, `HOME=<home>`, the fixed settings, and `PYTHONPATH` = the unit venv's own site-packages
     **first**, then the extra paths (for example the compat and blueprint sources), joined with `:`. This mirrors the
     template's `environment()`. `home` has no default: as in the Phase 7 harness, the run harness supplies a
     run-scoped home, so no new value is introduced (the template's `/nonexistent-inference-home` default is not
     copied).
   - **D-3 Fixed settings.** Every unit: `PYTHONDONTWRITEBYTECODE=1`. The U4 unit (`adas-hpc`, the inference host of
     WP-11 §4.1) additionally takes the template's three inference settings, `ORT_DISABLE_TELEMETRY=1`,
     `OMP_NUM_THREADS=1` and `OPENBLAS_NUM_THREADS=1`, unchanged from the template. No other unit takes them, since no
     other unit loads ONNX Runtime or a BLAS (WP-11 §4.1).
   - **D-4 Names derived from the values.** `environmentNames` is generated as `sorted(...)` of the keys
     `unit_environment` returns (the Phase 7 rule `sorted(unit.environment)`), so names and values cannot diverge:
     `HOME`, `PATH`, `PYTHONDONTWRITEBYTECODE`, `PYTHONPATH` for six units, and those plus the three inference names
     for `adas-hpc`.
   - **D-5 Declared composition.** The binding's evidence limitation states the flags and the `PYTHONPATH`
     composition (venv site-packages first), so the committed document records it. The limitation is free text that
     the schema admits.
   - **D-6 Checker.** `check_topology.py` gets a new check `unit-commands` per arm and form (and for the 7-unit
     variant): every binding's `arguments` start with the three flags followed by `-m` and the unit module, and its
     `environmentNames` equal the derived names. Existing checks are unchanged.
3. **What changes downstream (to be measured, not estimated).**
   - All 8 committed `deployment.json` files change, and so all 8 plan digests (V01) change. The other documents
     (`system.json`, `scenario.json`, components and profiles) are not touched.
   - The encoded persistence-configuration sizes of the admission dry run grow by a few bytes per unit. The baseline
     at `18201fe` (this host, rc.1 profiles, `/dev/shm/compat-p6-venv/bin/python -I -B check_topology.py`, report
     kept in scratch) is:

     | Arm (units) | op 0.29 s | op 0.25 s | op 0.2 s | slim |
     | --- | --- | --- | --- | --- |
     | comparator (5) | 150 053 | 150 028 | 150 024 | 65 951 (0.29) |
     | mloc (6) | 174 586 | 174 544 | 174 558 | 75 605 (0.29) |
     | mloc-7unit (7) | — | 186 358 | 186 383 | 87 866 (0.25) |

     The baseline plan digests and `deployment.json` sha256 values at `18201fe` are recorded in finding 2 next to the
     new ones.
   - **Records that pin these values** (none is edited by this increment; the thesis repository is read-only here):
     - thesis `decisions.md` row "WP-12 forms and C1 sizing" (146 458 / 170 503 / 182 302 B and "about 1.44×
       margin" under C1's 262 144 B);
     - `docs/review-wp12.md` findings 5 and 6 and `docs/evidence/wp12-check-5e53a54.json` (150 053 / 174 586 /
       186 358 B), which are historical evidence of `5e53a54`;
     - platform `docs/engineering/maestro-lite/review-c1.md` finding 1 (the `phase8` stand-in with "three environment
       names" and the Phase 7 argument vector; its margin covers "longer Phase 8 names and arguments");
     - thesis `design/wp10-fault-relay.md` §inputs, which cites blueprints main `5f71cde` as its form basis.
4. **Tests (offline only).** A parametrised argv test over every generated unit of every arm, both forms and the
   7-unit variant; a test that `unit_environment` puts the site-packages first and returns exactly the declared names;
   a negative test that the new check fails on a `-B`-only command; the full blueprint suite with
   `XVERSE_PLATFORM_PROFILES` set to the rc.1 export; `__pycache__` removed afterwards. Mutation probes: revert the
   flags to `-B` only; drop `PYTHONDONTWRITEBYTECODE` from the names; put the site-packages last.
5. **Out of scope.** No unit, simulator, Maestro run or live run; no download; the Phase 7/S1 units are not changed
   (a declared 1.0 limit until after the soak); the unit modules `assured_aeb.units.*` still do not exist (WP-13 to
   WP-17); no protocol value is introduced.

## Finding 2: implementation result (2026-10-24 16:05:32; commit `7b92e22`; report `docs/evidence/wp12b-check-7b92e22.json`)

1. **What changed** (`7b92e22`, on `e68a514`).
   - `topology.py`: constants `INTERPRETER_FLAGS = ("-S", "-s", "-B")`, `FIXED_ENVIRONMENT =
     {"PYTHONDONTWRITEBYTECODE": "1"}`, `INFERENCE_UNIT = "adas-hpc"` and `INFERENCE_ENVIRONMENT` (the template's three
     settings); functions `unit_module`, `unit_arguments`, `fixed_environment`, `unit_environment(unit, site_packages,
     *, home, extra_paths=())` and `environment_names`. `deployment()` now emits `unit_arguments(unit)` and
     `environment_names(unit)`, and adds one evidence limitation stating the flags and the `PYTHONPATH` composition.
     Standard library only; nothing is imported from the WP-08b branch.
   - `check_topology.py`: `REQUIRED_FLAGS`, `REQUIRED_NAMES` and `INFERENCE_NAMES` stated as literals, independently
     of the generator; `check_unit_command(docs)` and the new check `unit-commands` (8 arm/form cases and the 7-unit
     variant), run after `drift`. No existing check changed.
   - `xdl/<arm>/<form>/deployment.json` (all 8) regenerated with the **recorded** pins (`T.write(T.read_pins())`), so
     `xdl/pins.json` is unchanged. The base `pins` check showed no host drift. No other document changed.
   - `tests/test_topology.py`: 112 new test cases:
     - the argv and names test over every unit of the generated documents (4 arms × 2 forms, plus the 7-unit
       variant) and of the committed documents;
     - a coverage test (every unit of every arm, including `chassis-brake`, is seen);
     - `unit_environment` for each of the 7 units (site-packages first, names equal to the keys, inference settings
       only on `adas-hpc`);
     - no default `home`;
     - 4 negative cases of the check (`-B` only, missing `PYTHONDONTWRITEBYTECODE`, an extra name, reordered flags).
2. **Results (offline; host load 5.7 to 7.8).**
   - Blueprint suite: `XVERSE_PLATFORM_PROFILES=<scratch rc.1 export of 64ff9d3eb>/xdl/profiles
     /dev/shm/compat-p6-venv/bin/python -I -m pytest -q -p no:cacheprovider tests`: **399 passed** (287 at base,
     plus 112). `__pycache__` was removed afterwards, and none remains.
   - `check_topology.py`: exit 0 with **59 checks** passed (50 at base, plus 9 `unit-commands`).
   - Mutation probes (each restored byte-for-byte afterwards, checked with `cmp`), over the new tests and the drift
     test:

     | Probe | Result |
     | --- | --- |
     | P1 `INTERPRETER_FLAGS = ("-B",)` | 54 failed |
     | P2 `FIXED_ENVIRONMENT = {}` | 61 failed |
     | P3 site-packages last in `PYTHONPATH` | 7 failed |
     | P4 inference settings on every unit | 51 failed |
     | P5 checker `REQUIRED_FLAGS = ["-B"]` | 4 failed (the negative cases) |
     | P6 a default `home` | 1 failed |

3. **Old and new values.**
   - Plan digests (V01, deterministic over two compilations in both runs):

     | Arm | Form | `18201fe` | `7b92e22` |
     | --- | --- | --- | --- |
     | comparator | topology | `1ee2a677a8f0…` | `4b278fad86c7…` |
     | comparator | maestro | `3035c05ab0da…` | `5c42cb216c93…` |
     | mloc | topology | `4932d1c5dbe4…` | `351920ca9c50…` |
     | mloc | maestro | `555991157a9b…` | `4e8bee49df0d…` |
     | authorization-bypass | topology | `815f7c5d0015…` | `43cca03b749a…` |
     | authorization-bypass | maestro | `d49c237656b0…` | `cf47983619c0…` |
     | verification-bypass | topology | `d940d9d55d9c…` | `59e5ed8af8a7…` |
     | verification-bypass | maestro | `c00a4e2e8de0…` | `66ed5c00dafc…` |

     The full values are in the base report (scratch) and in `docs/evidence/wp12b-check-7b92e22.json`.
   - `deployment.json` sha256, base → new: comparator topology `22c6bd8d…` → `a8d35b8a…`, maestro `58bee16f…` →
     `9dce82ab…`; mloc topology `a134b38c…` → `509181fd…`, maestro `b748acfb…` → `0a7d6fdf…`;
     authorization-bypass topology `f1eb6585…` → `32302328…`, maestro `51d3d292…` → `30b1ec15…`;
     verification-bypass topology `edc7ccbd…` → `ca34314d…`, maestro `9143823c…` → `e275d4f8…`.
   - Encoded persistence-configuration bytes (full Maestro form, admission dry run):

     | Arm (units) | op | `18201fe` | `7b92e22` | Δ |
     | --- | --- | --- | --- | --- |
     | comparator (5) | 0.29 | 150 053 | 151 263 | +1 210 |
     | mloc (6) | 0.29 | 174 586 | 176 025 | +1 439 |
     | mloc-7unit (7) | 0.25 | 186 358 | 188 026 | +1 668 |
     | slim, 5 / 6 / 7 | 0.29 / 0.29 / 0.25 | 65 951 / 75 605 / 87 866 | 67 161 / 77 044 / 89 534 | |

     The growth is about 240 B per unit, mostly the new limitation string. **Observation:** the dry-run size varies by
     a few bytes between runs of the same commit (7 units at op 0.2 s: 188 049 and then 188 051), because the
     synthetic permit nonce contains `time.time_ns()`. The values above are from the committed report.
   - Against C1's proposed 262 144 B bound, the 7-unit full form leaves a margin of **1.394×** (1.407× at `18201fe`).
4. **Downstream records that pin the old values** (none is edited here; each needs its owner's update):
   - thesis `decisions.md` row "WP-12 forms and C1 sizing" (146 458 / 170 503 / 182 302 B; "about 1.44× margin").
     These figures were already out of date at `5e53a54` (186 358 B, 1.407×). Recommended update: 151 263 / 176 025 /
     188 026 B at `7b92e22`, margin 1.394×, citing this finding.
   - `docs/review-wp12.md` findings 5 and 6 and `docs/evidence/wp12-check-5e53a54.json`. These are historical evidence
     of `5e53a54` and stay as they are.
   - platform `review-c1.md` finding 1: its `phase8` stand-in declares three environment names and the Phase 7
     argument vector. The real form now declares four names (seven on U4) and two more arguments. This is inside the
     "longer Phase 8 names and arguments" that its margin covers, and the measured 188 026 B is the input C1 should
     cite.
   - thesis `design/wp10-fault-relay.md` cites blueprints main `5f71cde` for the fault-admission code. It does not
     cite a form digest, so no pin breaks. WP-10 #5 (wiring) should cite the forms after WP-12b merges.
   - Nothing else pins a WP-12 plan digest or `deployment.json` digest: a search of thesis `specs/002-assured-aeb`
     and of this blueprint's docs found only the records above.
5. **Correction to finding 1 D-3.** The reason given there, "no other unit loads ONNX Runtime or a BLAS (WP-11
   §4.1)", overstates its source. WP-11 §4.1 allocates modules, not packages. The supporting evidence is an import
   scan:
   - the current `assured_aeb/*.py` modules import only the standard library;
   - the compat sources import `numpy` or `onnxruntime` only in `xverse_compat/inference/` (the U4 code).

   The design is unchanged: the three inference settings stay on U4 only, as in the template. **Residual R-1:** if a
   later unit imports `numpy` (for example the U1 CARLA client or the U2 imaging stage), whether its thread settings
   are fixed must be decided in that unit's increment.
6. **Residuals.**
   - **R-2.** The unit modules `assured_aeb.units.*` and their venvs do not exist yet (WP-13 to WP-17). The harness that
     calls `unit_environment` comes with them. No `-S` launch of a Phase 8 unit has been exercised.
   - **R-3.** `-S` also removes `site`'s `.pth` processing for the unit venv itself. A venv whose packages need
     `.pth` files (namespace or editable installs) will not import under `-S`. Each unit venv must be checked for
     this when it is built (as WP-08 and WP-09 #3 did for U4).
   - **R-4.** The Phase 7/S1 units are unchanged (a declared 1.0 limit; S1e after the soak).
7. **Status.** This is ready for an independent read-only review. It has not been reviewed, accepted or merged.

## Finding 3: independent read-only Codex review (2026-10-24), PASS

Reviewed candidate `793dc0a020e26ead1164dceb1e91dbac68ef6c68` against the isolated-command decision,
the complete generator/checker/test diff and the regenerated deployment documents. No product repair was made.
The checker states argv and environment requirements independently of the generator. Existing pins and non-deployment
XDL documents are unchanged. The harness remains responsible for supplying the values; this is no claim of a live
unit launch. Finding 2 residuals R-1 to R-4 are carried.

Re-ran the complete blueprint suite from `automotive/assured-aeb`, using rc.1 profile schemas exported read-only
from platform tag `xverse-lite-v1.0.0-rc.1` and the pinned test interpreter:
`env PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 XVERSE_PLATFORM_PROFILES=<rc.1>/xdl/profiles
/dev/shm/compat-p6-venv/bin/python -I -B -m pytest -q -p no:cacheprovider tests --tb=short`.
Result: **399 passed**, no skip, in 31.01 s. Separately ran `check_topology.py` with the same profile directory:
exit 0, **59 PASS lines**, no failing check. `git diff --check` passes.
The generated-form digest and sizing changes remain recorded in finding 2; historical measurements are not rewritten.
No protocol values, Phase 7/S1 commands, rc.1 worktrees or soak inputs changed.
Suite-log SHA-256: `397dcccbb6d773c659a072aadfc51f2d07e70a478cb9084abc0eddfdb158cf19`.
