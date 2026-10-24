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
