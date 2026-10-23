"""Lite CARLA closed-loop integration run under Maestro (Phase 7; engineering integration, not AEB
validation). One test = one run. Configuration comes from environment variables set by ``run-live.sh``:

- ``XVERSE_LIVE_RUN_DIR``: evidence directory (loop10);
- ``XVERSE_COMPAT_SRC``: the xverse-compat checkout (adapters and descriptors);
- ``XVERSE_LIVE_CASE``: ``nominal`` | ``no-carla`` | ``cancel-paused`` | ``freeze-vcu`` | ``long-run`` (S1 FR-018).

The run: XDL documents -> validation and experiment plan -> ``prepare_lifecycle`` -> owned permits and
approvals (DLG-7: non-M1) -> schedule, coverage and collection admissions -> sealed helper images and
bootstrap -> ``_OriginalRuntimeRun.start``. Maestro writes its own Argus evidence; the driver writes the
flow evidence; results are written before any assertion.

S1c-2 part 2 (S1c finding 40; platform S1b; thesis FR-018): every unit declares a bounded TERM grace and private
stderr capture, each owned unit declares the ``nonce-marker`` readiness probe, and the harness asserts that the
owned units exit on TERM at their scheduled stops and that their readiness evidence carries the marker probe.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import copy
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
import threading
import time

import pytest

from xverse.maestro.admission import PermitApproval, PermitBinding, permit_digest
from xverse.maestro.artifacts import ArtifactDeclaration
from xverse.maestro.bootstrap import BootstrapAdmission, encode_bootstrap, seal_helper_image
from xverse.maestro.bootstrap_launcher import OriginalBootstrapRegistry
from xverse.maestro.collection_plan import admit_collection
from xverse.maestro.coverage import ArtifactExpectation, admit_coverage
from xverse.maestro.persistence import PersistenceClient, encode_configuration
from xverse.maestro.prbc import BoundaryDescriptor
from xverse.maestro.projection import Limits, ProviderDescriptor, prepare_lifecycle
from xverse.maestro.providers import ProbePolicy
from xverse.maestro.public_blobs import admit_broker_artifact
from xverse.maestro.run_broker import UnitAdmission
from xverse.maestro.runtime_entry import RuntimeScope, _OriginalRuntimeRun
from xverse.maestro.schedule_plan import admit_schedule
from xverse.maestro.time import HostDeadline
from xverse_xdl.lifecycle import ExecutionPermit
from xverse_xdl.validate import validate_sources

from tests.thesis_lite.maestro.test_bootstrap_launcher import pin
from tests.thesis_lite.maestro.test_preparation import SCHEMAS, documents as fixture_documents

sys.path.insert(0, str(Path(__file__).resolve().parent))
from units import units as unit_definitions  # noqa: E402

RUN_ID = "lite-carla-closed-loop"
# Maestro schedule ticks. A dispatcher cycle is not wall-time paced: it measured ~0.29 s per tick with four
# service calls at host load ~9 (lite-20261023T002003), and is at least poll_seconds. Persistence appends
# slow down as the evidence stream grows (live finding 03: ~2.8 events per tick, appends beyond the 0.38 s
# budget after ~270 events). Events are ~1 per tick plus health probes at a fixed wall rate, and slower
# appends lengthen each tick, so the run is kept short. Cycles measured 0.17 s per tick at load ~7 and
# 0.3-0.7 s at load 9-10.5: 80 ticks span ~14-55 s, covering the 9.5 s driver episode plus ~2 s startup.
# After S1a the cycle runs at the 0.05 s poll floor (steady mean ~0.057 s; the platform caps poll_seconds at
# 0.05 s), so tick counts are derived from that floor (S1c findings 15, 16 and 19). Tick 0 came 1.5-2.9 s after
# start and its start cycle took 0.9-2.1 s in the runs measured (S1c findings 22 and 24). 400 ticks last >= 20 s
# after tick 0; the driver episode ends ~11.5 s and the cancel-paused cancel ~12.3 s after tick 0. The 55 s active window, less the start and the stop/cleanup
# budget, holds 400 ticks while the mean cycle stays <= ~0.12 s. The S-D1 long-run horizon is S1c-2 scope.
HORIZON = 400
# S1 FR-018 / S-D1 (revised 600 Maestro ticks, 4 units): >= 30 s after tick 0 at the floor and inside the 55 s active
# window while the mean cycle stays <= ~0.085 s (measured 0.055-0.068 s). The driver episode (25 s) covers the
# long-run stimulus profile (three standard cycles, 21 s, from ~1.5 s after the episode starts); events ~800 < 8192
# and retained inputs ~1.3 MB (measured) < RETAINED_MAX.
LONG_RUN_HORIZON, LONG_RUN_EPISODE_S = 600, 25.0
# Observe at tick 60 (~7 s after start at the floor): before the cancel-paused cancel (>= 13.2 s after start) up to
# a ~0.15 s mean cycle, so that case always completes observe before the cancel (S1c finding 19, MEDIUM-3).
OBSERVE_TICK = 60
# The thaw must come <= cadence 5 s - health_scan_seconds 1.52 s = 3.48 s after the VCU's last health success
# (S1c finding 18). Without the observe probe that success can be up to ~1.7 s (measured gap) before the freeze;
# 10 ticks (0.50-1.00 s measured) keep the worst case inside the bound up to a ~0.15 s mean cycle (S1c findings 19
# and 24). Tick 40 fell only 0.08-0.89 s after the stimulus throttle start (a ~3.45 s segment), so the freeze is
# ~1.1-2.0 s into the segment (finding 22). It starts at tick 61, one tick after the observe at tick 60, so that
# observe really probes the VCU (a frozen unit's probe returns its cached observation; finding 24, MEDIUM-1).
# The case fails unless the freeze lies inside the throttle segment (finding 24, LOW-1).
FREEZE_AT, FREEZE_TICKS = 61, 10
RETAINED_MAX = 4 * 1024 * 1024  # ~2.2 KB per event, ~560 events at 400 ticks; above the 1 MiB default
POLL = 0.05
# S1c-2 part 2 (S1c finding 40; platform S1b, thesis FR-018). Every unit, the legacy VCU included, declares a TERM
# grace of 0.6 s: inside ML-SCHEDULE-STOP-GRACE, grace + STOP_FORCE_RESERVE 0.5 <= NORMAL_SHARE 0.6 x per_unit_seconds 2
# = 1.2 s. The graceful stop applies to the scheduled stop steps only; the terminal fence after a cancel stays forced
# (platform D-1, thesis DR-7). Every unit's stderr is a private run-scoped file of at most 256 KiB (D-3, DR-9).
STOP_GRACE_S = 0.6
STDERR_CAPTURE = {"capture": "run-scoped-private", "maximumBytes": 256 * 1024}
MARKER_PROBE = "nonce-marker"
# The readiness window is W = min(probe-policy timeout, observe action timeout); three marker attempts span it, the
# last at W - 0.25 s (platform S1b finding 10). With the fixture's 1 s timeout the last attempt would come 0.75 s after
# release. The adapter is ready only once CARLA, its owned scenario and its link are set up: its owned-actor registry
# was written 0.24-1.26 s after its release in the S1c-2 part 1 runs (load 6.3-8.5). The owned units' timeout is
# therefore the declared observe budget, 2 s (attempts at 0, 0.875 and 1.75 s); the VCU keeps the fixture's 1 s.
OWNED_READINESS_TIMEOUT_S = 2.0
ORDER = ("lite-driver", "carla-adapter", "legacy-vcu", "driver-stimulus")
# the fixture's flow source starts first: the driver is the source of the actuation-command flow to the adapter
RENAME = {"source-instance": "lite-driver-instance", "sink-instance": "carla-adapter-instance",
          "source-binding": "lite-driver-binding", "sink-binding": "carla-adapter-binding",
          "sample-loop": "lite-carla-closed-loop", "local-simulated-loop": "lite-carla-closed-loop-local",
          "sample-observation-run": "lite-carla-closed-loop-run",
          # review 1 R-5: meaningful names for the fixture-derived elements (the structure stays the fixture's)
          "sample-flow": "actuation-command-flow", "sample-observer": "lite-run-observer", "sample-count": "completion-markers",
          "sample-source": "lite-runtime-unit"}
FIXTURE_TEXT = {  # declared text replaced so that the plan does not describe an offline sample
    "Demonstrate offline declared intent compilation only.":
        "Engineering integration: Maestro lifecycle of the Lite CARLA closed loop; collection of every owned completion marker.",
    "Declared intent only; no runtime result is claimed.": "Engineering integration only; not AEB validation, not M1.",
}
ENVIRONMENT_DIGEST = pin(b"owned-environment")


def _rename(value):
    text = json.dumps(value)
    for old, new in FIXTURE_TEXT.items():
        text = text.replace(json.dumps(old), json.dumps(new))
    for old, new in RENAME.items():
        text = text.replace(f'"{old}"', f'"{new}"').replace(f'/{old}"', f'/{new}"').replace(f'/{old}#', f'/{new}#')
    return json.loads(text)


def build_documents(defs, artifacts, horizon=HORIZON):
    """Derive the blueprint's XDL documents from the platform's validated fixture set."""

    docs = _rename(fixture_documents())
    # S1b: process.stop and process.stderr exist in the runtime-compatibility profile v0.2 only; the fixture is v0.1.
    # The profile document and every binding payload move to v0.2 as in the platform's own S1b tests (declare()).
    profile = docs["runtime-profile.json"]
    profile["metadata"]["version"] = "0.2.0"
    profile["spec"]["schemaRef"] = "https://xverse.io/profiles/runtime-compatibility/v0.2/schema.json"
    system = docs["system.json"]["spec"]
    template_instance = next(i for i in system["componentInstances"] if i["id"] == "lite-driver-instance")
    template_node = system["nodes"][1]
    for name in ("legacy-vcu", "driver-stimulus"):
        system["componentInstances"].append(dict(copy.deepcopy(template_instance), id=name + "-instance", nodeId=name + "-node"))
        system["nodes"].append(dict(copy.deepcopy(template_node), id=name + "-node"))
    deployment = docs["deployment.json"]["spec"]
    template_binding = next(b for b in deployment["bindings"] if b["id"] == "lite-driver-binding")
    for name in ("legacy-vcu", "driver-stimulus"):
        binding = copy.deepcopy(template_binding)
        binding["id"] = name + "-binding"
        binding["logicalRef"]["element"] = name + "-instance"
        binding["extensions"]["io.xverse.experiment"]["target"]["element"] = name + "-binding"
        deployment["bindings"].append(binding)
    deployment["artifacts"] = [dict(id=key, artifactKind="executable", version="1.0.0", digest=digest, sourceRef=Path(path).as_uri(),
                                    maturity="prototype") for key, (path, digest) in artifacts.items()]
    by_name = {d.name: d for d in defs}
    for binding in deployment["bindings"]:
        unit = by_name[binding["id"].removesuffix("-binding")]
        binding["artifactIds"] = ["python310" if unit.executable.endswith("python3.10") else "python313"]
        payload = binding["extensions"]["io.xverse.runtime.compatibility"]
        payload["provider"] = {"id": "maestro-process-v1", "kind": "process"}
        payload["schemaVersion"] = "0.2.0"  # profile v0.2 (above)
        # declared action budgets (the schedule uses them: use_action_timeouts); 5 s is the platform cap.
        # A killed legacy VCU (many zenoh threads) needs more than the fixture's 1 s to be reaped.
        for action in payload["actions"]:
            action["timeoutSeconds"] = {"prepare": 2, "start": 5, "observe": 2, "stop": 5, "cleanup": 5}[action["phase"]]
        payload["process"] = {"executable": unit.executable, "arguments": list(unit.arguments), "workingDirectory": unit.working_directory,
                              "environmentNames": sorted(unit.environment), "inheritedHandles": "closed", "implicitShell": False,
                              "stop": {"graceSeconds": STOP_GRACE_S}, "stderr": dict(STDERR_CAPTURE)}  # S1b, every unit
        if unit.owned:  # S1b nonce-marker readiness for the owned units; the legacy VCU stays liveness-only (running)
            for action in payload["actions"]:
                if action["phase"] == "observe":
                    action["condition"] = MARKER_PROBE
    scenario = docs["scenario.json"]["spec"]
    template = scenario["steps"][0]
    scenario["steps"] = []
    plan = []
    for index, name in enumerate(ORDER):
        before = [f"start-{ORDER[index - 1]}"] if index else []
        plan += [(f"prepare-{name}", name, "prepare", 0, []), (f"start-{name}", name, "start", 0, [f"prepare-{name}"] + before),
                 (f"observe-{name}", name, "observe", OBSERVE_TICK, [f"start-{name}"])]
    stops = {"driver-stimulus": horizon - 3, "legacy-vcu": horizon - 2, "carla-adapter": horizon - 1, "lite-driver": horizon}
    for name, tick in stops.items():
        plan += [(f"stop-{name}", name, "stop", tick, [f"observe-{name}"]), (f"cleanup-{name}", name, "cleanup", tick, [f"stop-{name}"])]
    for step_id, unit, phase, tick, deps in plan:
        step = copy.deepcopy(template)
        step["id"] = step_id
        step["targetRef"]["element"] = unit + "-instance"
        step["actionKind"] = "validate" if phase == "prepare" else phase
        step["action"]["operation"] = step["actionKind"]
        step["schedule"]["at"] = tick
        ext = step["extensions"]["io.xverse.experiment"]
        ext["target"]["element"] = step_id
        ext["phase"] = phase
        ext["dependsOn"] = deps
        scenario["steps"].append(step)
    return docs


def compile_documents(docs):
    from xverse_xdl.experiment_plan import compile_experiment_plan  # noqa: PLC0415

    validation = validate_sources([(name, json.dumps(value).encode()) for name, value in docs.items()], profile_schema_paths=SCHEMAS)
    assert validation.is_valid, [(d.code, d.message) for d in validation.diagnostics]
    result = compile_experiment_plan(validation.resources)
    assert result.is_valid, [(d.code, d.message) for d in result.diagnostics]
    return result, validation.resources


def _fact(compute):
    """One closure fact as JSON data (dataclasses as dicts, None as null), or ``{"error": ...}`` if it fails."""

    from dataclasses import is_dataclass  # noqa: PLC0415

    def plain(value):
        if is_dataclass(value) and not isinstance(value, type):
            return {k: plain(v) for k, v in asdict(value).items()}
        if isinstance(value, (list, tuple)):
            return [plain(v) for v in value]
        if isinstance(value, dict):
            return {str(k): plain(v) for k, v in value.items()}
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        return repr(value)

    try:
        return plain(compute())
    except Exception as error:  # noqa: BLE001 - a fact must never cost the run record
        return {"error": f"{type(error).__name__}: {error}"}


def _tick_timing(events, start_ns):
    """First host time of each schedule tick, from the Maestro Argus stream (S1c finding 16).

    The tick-0 start cycle is reported apart from the steady cycles (S1c finding 19, LOW-4)."""

    first = {}
    for line in events.read_text().splitlines():
        clocks = json.loads(line).get("clocks") or {}
        if "simulation" in clocks:
            first.setdefault(clocks["simulation"]["value"], clocks["host"]["value"] - start_ns / 1e9)
    ticks = sorted(first)
    if len(ticks) < 2:
        return {"ticks": len(ticks)}
    cycles = [first[b] - first[a] for a, b in zip(ticks, ticks[1:])]
    steady = cycles[1:] or cycles
    return {"ticks": len(ticks), "lastTick": ticks[-1], "firstTickS": round(first[ticks[0]], 3), "lastTickS": round(first[ticks[-1]], 3),
            "startCycleS": round(cycles[0], 4), "meanCycleS": round(sum(steady) / len(steady), 4), "maxCycleS": round(max(steady), 4)}


def _freeze_overlap(events, stimulus):
    """Seconds of the freeze (Argus apply..clear) inside the stimulus's own throttle window (host-monotonic)."""

    marks = {}
    for line in events.read_text().splitlines():
        event = json.loads(line)
        text = (event.get("annotation") or {}).get("text") or ""
        for phase in ("apply", "clear"):
            if text.startswith("fault ") and f" {phase} " in f"{text} ":
                marks.setdefault(phase, event["clocks"]["host"]["value"])
    pedal = [r for r in (json.loads(x) for x in stimulus.read_text().splitlines()[1:]) if r.get("acc", 0) > 0]
    if len(marks) != 2 or not pedal:
        return {"marks": marks, "pedalSamples": len(pedal), "overlapS": None}
    s0, s1 = pedal[0]["monotonicNs"] / 1e9, pedal[-1]["monotonicNs"] / 1e9 + 0.05  # the last sample's 50 ms period
    return {"appliedS": marks["apply"], "clearedS": marks["clear"], "throttleWindowS": [s0, s1],
            "overlapS": round(min(marks["clear"], s1) - max(marks["apply"], s0), 3),
            "startMarginS": round(marks["apply"] - s0, 3), "endMarginS": round(s1 - marks["clear"], 3)}


def _argus_verify(root):
    """``xverse-argus verify`` of one evidence root, next to this interpreter (S1c finding 22, MEDIUM-2)."""

    tool = Path(sys.executable).parent / "xverse-argus"
    done = subprocess.run([str(tool), "verify", str(root)], capture_output=True, text=True, timeout=60, check=False)
    data = json.loads(done.stdout)
    return {"exit": done.returncode, "writerState": data.get("writerState"), "evidenceStatus": data.get("evidenceStatus"),
            "evidenceReasons": data.get("evidenceReasons"), "diagnostics": [d.get("code") for d in data.get("diagnostics") or []]}


TERMINAL_RPC_KINDS = {"init", "terminal-report", "closure", "abort", "collect", "public-export", "public-blob"}


def _persistence_timing(timings):
    """The FR-002 per-event metric over ordinary persistence calls; start-up and terminal calls apart (S1a bench)."""

    ordinary = [ns / 1e9 for kind, ns in timings if kind not in TERMINAL_RPC_KINDS]
    terminal = [(kind, round(ns / 1e9, 4)) for kind, ns in timings if kind in TERMINAL_RPC_KINDS]  # all, in call order
    if not ordinary:
        return {"count": 0, "terminalCallsS": terminal}
    ordered, n = sorted(ordinary), len(ordinary)
    deciles = [ordinary[i * n // 10:(i + 1) * n // 10] for i in range(10)]
    means = [sum(d) / len(d) for d in deciles if d]
    return {"count": n, "p99S": round(ordered[max(0, int(n * .99) - 1)], 4), "maxS": round(ordered[-1], 4),
            "firstDecileMeanS": round(means[0], 4), "lastDecileMeanS": round(means[-1], 4),
            "lastDecileIncreaseS": round(means[-1] - means[0], 4), "terminalCallsS": terminal}


def _digest(path):
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _short(unit_id):
    """``lite-driver`` for ``xdl://...#componentInstances/lite-driver-instance``."""

    return str(unit_id).rsplit("/", 1)[-1].removesuffix("-instance")


def _stop_modes(native):
    """Each unit's S1b ``stop_mode`` (``exited-on-term`` or ``forced``) from the recorded native closure facts."""

    return {_short(u["unit_id"]): u.get("stop_mode", "field-absent") for u in native}


def _readiness_probes(events):
    """The probe identities of the unit-scope readiness (probe, ready) and health annotations in the Maestro Argus
    stream (S1b: probe and ready carry the declared identity; health stays running)."""

    out = {}
    for line in events.read_text().splitlines():
        x = (json.loads(line).get("extensions") or {}).get("xverse.maestro") or {}
        if x.get("scope") != "unit" or not x.get("unitId") or x.get("action") not in ("probe", "ready", "health", "health-loss"):
            continue
        row = out.setdefault(_short(x["unitId"]), {"probe": [], "ready": [], "healthProbeIds": []})
        if x["action"] in ("probe", "ready"):
            row[x["action"]].append([x.get("outcome"), x.get("probeId")])
        elif x.get("probeId") not in row["healthProbeIds"]:
            row["healthProbeIds"].append(x.get("probeId"))
    return out


def _stderr_sizes(directories):
    """Sizes of the private stderr files (names and sizes only; never their content or their paths; D-3)."""

    return {name: {e.name: e.stat(follow_symlinks=False).st_size for e in os.scandir(path)} for name, path in directories.items()}


def stderr_directories(run_dir, names):
    """S1b private stderr directories ``<run>/stderr-private/<unit>/``: mode 0700, empty, distinct, outside the
    collection source root (the work root is on tmpfs, the run directory on loop10). The path is resolved, because
    the platform opens it component by component without following links."""

    root = Path(run_dir).resolve() / "stderr-private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    directories = {}
    for name in names:
        path = root / name
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        directories[name] = path
    return directories


def test_live_closed_loop(environment, binaries, authority_binary, run_bootstrap_binary, tmp_path, monkeypatch):
    run_dir = Path(os.environ["XVERSE_LIVE_RUN_DIR"])
    compat = Path(os.environ["XVERSE_COMPAT_SRC"])
    case = os.environ.get("XVERSE_LIVE_CASE", "nominal")
    for sub in ("home", "carla-home", "driver"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    record = {"runId": RUN_ID, "case": case, "nonM1": True, "startedWallNs": time.time_ns(), "monotonicStartNs": time.monotonic_ns(),
              "loadAverageStart": list(os.getloadavg()),  # 1/5/15 min (S1c finding 19, MEDIUM-2)
              "harness": "owned trusted-host Maestro harness (_OriginalRuntimeRun); not RuntimeService, not M1 (DLG-7)",
              "syntheticPlaceholders": {"bootstrapApprovalRef": "bootstrap-approval (harness label, not an approval record)",
                                        "environmentDigest": "pin(b'owned-environment') (harness pin, as in the platform fixture)",
                                        "permitIssuer": "author-delegated-live-integration (integration-built trusted-host permit)"},
              "xdlLimits": "derived from the platform Maestro fixture structure: one schedule domain experiment-time; the runtime flows "
                           "(vehicle-motion, radar-adas) and the carla-simulation domain are bound in xverse_compat.live.loop, not planned (R-5)"}
    factory, _, _ = environment
    manager, _ = factory(seconds=95, run_id=RUN_ID, operation=2)
    work = tmp_path / "work"
    work.mkdir()
    socket_path = f"/run/user/{os.getuid()}/xverse-lite/{RUN_ID}.sock"
    Path(socket_path).parent.mkdir(parents=True, exist_ok=True)
    plan_path = run_dir / "experiment-plan.json"
    # a 9.5 s driver episode covers the stimulus start offset (~1.5 s measured) and its 7 s profile
    long_run = case == "long-run"
    defs = unit_definitions(compat=compat, run_dir=run_dir, work=work, socket_path=socket_path, plan=plan_path,
                            episode_s=LONG_RUN_EPISODE_S if long_run else 9.5,
                            pause_after_s=4.0 if case == "cancel-paused" else None,  # inside the throttle segment (review 2 N-3)
                            stimulus_profile="long-run" if long_run else "standard")
    stderr_dirs = stderr_directories(run_dir, [d.name for d in defs])  # before any helper is reserved
    artifacts = {"python310": ("/usr/bin/python3.10", _digest("/usr/bin/python3.10")),
                 "python313": (defs[0].executable, _digest(defs[0].executable))}
    horizon = LONG_RUN_HORIZON if long_run else HORIZON
    record["horizonTicks"] = horizon
    docs = build_documents(defs, artifacts, horizon)
    if case == "freeze-vcu":  # Phase 5 freeze (cgroup.freeze) of the legacy VCU unit; thaw on clear (automatic)
        from tests.thesis_lite.faults.support import fault  # noqa: PLC0415

        # the freeze spans the throttle phase (review: final run 011855 froze in the idle second); ticks per S1c finding 16
        freeze = fault("f-freeze-vcu", "freeze", "legacy-vcu-instance", at=FREEZE_AT, duration=FREEZE_TICKS, recovery="automatic")
        freeze = _rename(freeze)
        docs["scenario.json"]["spec"]["faults"] = [freeze]
        record["faults"] = [freeze]
    (run_dir / "xdl").mkdir(exist_ok=True)
    for name, value in docs.items():
        (run_dir / "xdl" / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    result, resources = compile_documents(docs)
    plan_path.write_text(json.dumps(result.plan, indent=2, sort_keys=True) + "\n")
    record["planDigest"] = result.plan.get("digest")
    # the provider pin is the run-authority helper image (the runtime fixture passes it as the launcher)
    helper_pin = "sha256:" + hashlib.sha256(authority_binary.read_bytes()).hexdigest()
    prepared = prepare_lifecycle(result, resources, provider_descriptors=(ProviderDescriptor("maestro-process-v1", "process", helper_pin,
                                                                                            "isolated-fixture"),),
                                 limits=Limits(horizon_ticks=horizon))
    record["units"] = [u.unit_id for u in prepared.units]
    now = datetime.now(timezone.utc)
    bindings, approvals = [], []
    for index, unit in enumerate(prepared.units):
        unit_plan = unit.plan
        legacy = "legacy-vcu" in unit.unit_id
        permit = ExecutionPermit(
            permit_id=f"live-permit-{index}", nonce=f"live-nonce-{index}-{time.time_ns()}", plan_digest=unit_plan.digest,
            catalog_identity=unit_plan.catalog_identity, environment_identity=unit_plan.environment_identity,
            permitted_actions=tuple(a.action_id for a in unit_plan.actions),
            approval_evidence_ref="urn:xverse:author:2026-10-22:live-integration-authorization", issuer_label="author-delegated-live-integration",
            operation_classes=tuple(sorted({a.operation for a in unit_plan.actions})), exclusions=() if legacy else ("legacy-execution",),
            public_safety_classification="public-safe", not_before=now - timedelta(seconds=30), expires_at=now + timedelta(seconds=150))
        binding = PermitBinding(unit.unit_id, f"live-execution-{index}", 1, permit)
        bindings.append(binding)
        approvals.append(PermitApproval(permit.approval_evidence_ref, permit.issuer_label, RUN_ID, unit.unit_id, binding.execution_id, 1,
                                        prepared.lifecycle_digest, unit_plan.digest, unit.provider.provider_id, unit.provider.kind, helper_pin,
                                        unit_plan.environment_identity, unit_plan.artifact_digests, permit_digest(permit),
                                        now - timedelta(seconds=30), now + timedelta(seconds=150)))
    # health capacity: period = cadence - n*op - (S+1)*op must exceed n*op; cadence <= 5 s, 4 units, S >= 4 (native controller) -> op < 0.385 s
    readiness_timeout = {u.unit_id: 1 if "legacy-vcu" in u.unit_id else OWNED_READINESS_TIMEOUT_S for u in prepared.units}
    schedule = admit_schedule(prepared, policies=tuple(ProbePolicy(u.unit_id, 5, 5, readiness_timeout[u.unit_id]) for u in prepared.units),
                              ticks=tuple(range(horizon + 1)), active_seconds=55, operation_seconds=0.38, service_operation_count=4, per_unit_seconds=2, poll_seconds=POLL,
                              request_limit=8192, event_limit=8192, use_action_timeouts=True)
    owned = [u for u in prepared.units if "legacy-vcu" not in u.unit_id]
    declarations = tuple(ArtifactDeclaration(u.unit_id, 1, u.binding_id + ".marker", "outputs/" + u.binding_id + ".txt") for u in owned)
    st = work.stat()
    coverage = admit_coverage(prepared, result, resources, run_id=RUN_ID, host_session="host-session",
                              contexts=[(b.unit_id, b.generation, b.execution_id) for b in bindings],
                              health_policies={p.unit_id: (p.cadence_seconds, p.freshness_seconds) for p in schedule.policies},
                              active_start=time.monotonic(), active_end=time.monotonic() + schedule.active_seconds,
                              source_digests=(pin(schedule.canonical_bytes),),
                              artifacts=[*(ArtifactExpectation(d.destination, True, 256, d.unit_id, 1) for d in declarations),
                                         ArtifactExpectation("collection-result.json", maximum_bytes=16384),
                                         ArtifactExpectation("retained-inputs.json", maximum_bytes=RETAINED_MAX)])
    collection = admit_collection(coverage, expected_digest=coverage.digest, source_root=str(work), source_identity=(st.st_dev, st.st_ino),
                                  declarations=declarations, metadata_path="collection-result.json", operation_seconds=1,
                                  per_unit_teardown_seconds=2, collection_seconds=3, terminal_seconds=2, drain_seconds=2)
    config = encode_configuration(prepared, result, resources, run_id=RUN_ID, bindings=bindings, approvals=approvals, session="host-session",
                                  generation_deadline=manager._admission.teardown_deadline, journal_path=tmp_path / "m3.jsonl",
                                  evidence_root=tmp_path / "argus-maestro", schedule=schedule, coverage=coverage, collection=collection,
                                  broker_artifact=admit_broker_artifact(coverage, expected_digest=coverage.digest))
    images = tuple(seal_helper_image(p, digest=pin(p.read_bytes()), argv0=sys.executable if p == Path(sys.executable).resolve() else str(p))
                   for p in (binaries["launcher"], binaries["bound-gate"], Path(sys.executable).resolve(), authority_binary))
    supervisor = seal_helper_image(run_bootstrap_binary, digest=pin(run_bootstrap_binary.read_bytes()), argv0=str(run_bootstrap_binary))
    lease = HostDeadline("host-session", time.monotonic() + 4.8)
    boot = encode_bootstrap(BootstrapAdmission(config.run_id, config.prepared.lifecycle_digest, "bootstrap-approval", ENVIRONMENT_DIGEST,
                                               supervisor.digest, manager._admission.teardown_deadline,
                                               lease, images[:3], images[3], manager._root_fd))
    launcher = OriginalBootstrapRegistry(1).reserve(boot, supervisor, manager)
    by_name = {d.name: d for d in defs}
    record["declaredControls"] = {"stopGraceSeconds": STOP_GRACE_S, "stderr": STDERR_CAPTURE, "ownedReadinessProbe": MARKER_PROBE,
                                  "ownedReadinessTimeoutS": OWNED_READINESS_TIMEOUT_S, "perUnitSeconds": config.schedule.per_unit_seconds}
    admissions = tuple(UnitAdmission(BoundaryDescriptor(config.run_id, u.unit_id, 1, "work-" + str(i), 0),
                                     tuple(sorted(by_name[u.binding_id.removesuffix("-binding")].environment.items())), 1,
                                     stderr_directory=str(stderr_dirs[u.binding_id.removesuffix("-binding")]))
                       for i, u in enumerate(config.prepared.units))
    entry = _OriginalRuntimeRun(config, launcher, admissions, controller_sessions=1)
    active = HostDeadline(config.session, config.coverage.data(config.coverage.digest)["end"] - .01)
    reserve = config.schedule.terminal_reserve_seconds + config.collection.collection_seconds + config.collection.terminal_seconds
    terminal = HostDeadline(config.session, active.monotonic_seconds + reserve + 1 + .01)
    closure = HostDeadline(config.session, min(terminal.monotonic_seconds + 3, time.monotonic() + 89.5, config.generation_ns / 1e9))
    # start-up ends just inside the bootstrap lease (the platform's upper bound), not 2 s from now: the controller worker
    # missed a 2 s start-up once at load 9-10 (platform S1b finding 2, GA-10; S1c finding 28)
    scope = RuntimeScope(HostDeadline("host-session", lease.monotonic_seconds - 0.05), active, terminal, closure)
    record["startupScopeS"] = round(lease.monotonic_seconds - 0.05 - time.monotonic(), 3)
    rpc_timings = []  # client-side persistence round trips, as in the S1a bench (measurement only; S1 P6, FR-002)
    original_rpc = PersistenceClient._rpc

    def timed_rpc(self, kind, body, deadline, **kwargs):
        began = time.monotonic_ns()
        try:
            return original_rpc(self, kind, body, deadline, **kwargs)
        finally:
            rpc_timings.append((kind, time.monotonic_ns() - began))

    monkeypatch.setattr(PersistenceClient, "_rpc", timed_rpc)
    record["budgets"] = {"terminalReserveS": config.schedule.terminal_reserve_seconds, "reserveS": reserve,
                         "closureFromNowS": round(closure.monotonic_seconds - time.monotonic(), 2)}
    record["scope"] = {"activeS": round(active.monotonic_seconds - time.monotonic(), 2), "terminalReserveS": config.schedule.terminal_reserve_seconds}
    outcome = None
    canceller = None
    run_ended = threading.Event()  # set when entry.start returns: a cancel is never issued after the run (S1c finding 15)
    if case == "cancel-paused":  # cancel while the simulation clock is paused (driver stopped ticking)
        def cancel():
            summary = run_dir / "driver" / "driver-summary.json"
            limit = time.monotonic() + 40
            while time.monotonic() < limit and not run_ended.is_set():
                try:
                    if json.loads(summary.read_text()).get("endReason") == "paused":
                        record["pauseSeenMonotonicNs"] = time.monotonic_ns()
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(0.2)
            # paused (synchronous, no tick) for 6 s of host time, beyond the 5 s probe freshness (R-6)
            if "pauseSeenMonotonicNs" not in record or run_ended.wait(6.0):
                record["cancelNotIssued"] = "run ended first" if run_ended.is_set() else "pause not seen within 40 s"
                return
            record["cancelRequestedMonotonicNs"] = time.monotonic_ns()
            record["cancelEpoch"] = entry.stop(RUN_ID, reason="operator-cancel-while-paused")
            record["cancelReturnedMonotonicNs"] = time.monotonic_ns()
        canceller = threading.Thread(target=cancel, daemon=True)
        canceller.start()
    try:
        outcome = entry.start(scope)
    finally:
        record["startReturnedMonotonicNs"] = time.monotonic_ns()  # before run_ended (S1c finding 19, LOW-3)
        run_ended.set()
        if canceller is not None:
            canceller.join(timeout=5)
            if canceller.is_alive():  # still waiting or in entry.stop: recorded, never silently dropped
                record["cancellerAliveAfterJoin"] = True
        record["loadAverageEnd"] = list(os.getloadavg())
        record["endedWallNs"] = time.time_ns()
        record["monotonicEndNs"] = time.monotonic_ns()
        if outcome is not None:
            record.update(executionSucceeded=_fact(lambda: outcome.execution_succeeded),
                          cleanupComplete=_fact(lambda: outcome.cleanup_complete),
                          diagnostics=_fact(lambda: list(outcome.diagnostics)),
                          dispatchDiagnostic=_fact(lambda: outcome.dispatch.diagnostic if outcome.dispatch else None),
                          steps=_fact(lambda: list(outcome.dispatch.steps) if outcome.dispatch else None),
                          normalUnitRecordsComplete=_fact(lambda: outcome.closure.normal_unit_records_complete),
                          nativeUnits=_fact(lambda: list(outcome.closure.native_units)),
                          # S1 FR-017: the facts that attribute a closure outcome (research R-2); each is computed
                          # by a guard so that a failing fact never loses this record or skips dispose()
                          persistenceFailure=_fact(lambda: outcome.persistence_failure),
                          closureDiagnostics=_fact(lambda: list(outcome.closure.diagnostics)),
                          closureWriters=_fact(lambda: list(outcome.closure.writers)),
                          closureTerminalReports=_fact(lambda: [_fact(r.public_data) for r in outcome.closure.terminal_reports]),
                          dispatchTerminal=_fact(lambda: outcome.dispatch.terminal.public_data()
                                                 if outcome.dispatch and outcome.dispatch.terminal is not None else None))
        record["workArtifacts"] = _fact(lambda: sorted(p.name for p in work.iterdir()))
        record["tickTiming"] = _fact(lambda: _tick_timing(tmp_path / "argus-maestro" / "events.jsonl", record["monotonicStartNs"]))
        record["argusMaestroVerify"] = _fact(lambda: _argus_verify(tmp_path / "argus-maestro"))
        record["persistenceTiming"] = _fact(lambda: _persistence_timing(rpc_timings))
        record["brokerCancelResult"] = _fact(lambda: entry._broker._cancel_result)  # confirmed or revoked (S1a-2 finding 24)
        # S1c-2 part 2: TERM outcome per unit, private stderr sizes, readiness probe identities (S1c finding 40)
        record["stopModes"] = _fact(lambda: _stop_modes(record["nativeUnits"])) if isinstance(record.get("nativeUnits"), list) else None
        record["stderrPrivateBytes"] = _fact(lambda: _stderr_sizes(stderr_dirs))
        record["readinessProbes"] = _fact(lambda: _readiness_probes(tmp_path / "argus-maestro" / "events.jsonl"))
        if case == "freeze-vcu":
            record["freezeThrottle"] = _fact(lambda: _freeze_overlap(tmp_path / "argus-maestro" / "events.jsonl", run_dir / "stimulus.jsonl"))
        markers = {}
        for p in work.glob("*.marker"):  # review 2 N-4: a marker records its unit's outcome, not only completion
            try:
                value = json.loads(p.read_text())
                markers[p.name] = value if isinstance(value, dict) else {"unreadable": True, "type": type(value).__name__}
            except (OSError, ValueError):  # a marker can never cost the run record (S1c finding 9, R3-4)
                markers[p.name] = {"unreadable": True}
        record["markerContents"] = markers
        record["markersOk"] = len(markers) == 3 and all(m.get("code") == 0 or m.get("outcome") == "profile-complete" for m in markers.values())
        (run_dir / "maestro-run.json").write_text(json.dumps(record, indent=2, sort_keys=True, default=str) + "\n")
        if outcome is not None:
            entry.dispose()
        else:
            launcher.dispose()
        for image in (*images, supervisor):
            os.close(image.descriptor)
    # every case asserts its expected path (S1c findings 15 and 19, MEDIUM-1) and its Maestro Argus root (finding 22)
    verified = record.get("argusMaestroVerify") or {}
    if case in ("nominal", "freeze-vcu", "long-run"):
        assert outcome.execution_succeeded and outcome.cleanup_complete and record["markersOk"], record.get("dispatchDiagnostic")
        assert verified.get("writerState") == "closed" and verified.get("evidenceStatus") == "complete", verified
    else:  # a failed writer whose only reason is its own state (proposed DR-6); P3 also allows closed (DR-2)
        assert verified.get("writerState") in (("failed", "closed") if case == "cancel-paused" else ("failed",)), verified
        assert set(verified.get("evidenceReasons") or []) <= {"ARGUS2-REASON-WRITER-STATE"}, verified
    native = record.get("nativeUnits")
    if isinstance(native, list):  # S1b: the field exists for every unit (platform S1b review MEDIUM-1 disposition)
        assert all("stop_mode" in u for u in native), native
    if case in ("nominal", "freeze-vcu", "long-run"):  # the owned units exit on TERM at their scheduled stops (FR-009)
        modes = record.get("stopModes") or {}
        assert all(modes.get(name) == "exited-on-term" for name in ORDER if name != "legacy-vcu"), modes  # the VCU: recorded only
    if case in ("nominal", "freeze-vcu", "long-run", "cancel-paused"):  # every unit started before any cancel
        probes = record.get("readinessProbes") or {}
        for name in ORDER:
            expected = "running" if name == "legacy-vcu" else MARKER_PROBE
            row = probes.get(name) or {}
            assert row.get("ready") and all(p == expected for _, p in row.get("probe", []) + row["ready"]), (name, row)
            assert row.get("healthProbeIds") in ([], ["running"]), (name, row)  # health stays liveness-only
    if case == "freeze-vcu":
        timing = record.get("freezeThrottle") or {}  # the freeze lies inside the throttle segment (finding 24, LOW-1)
        margins = (timing.get("startMarginS"), timing.get("endMarginS"))
        assert all(m is not None and m >= 0 for m in margins), timing
    if case == "no-carla":
        assert record.get("dispatchDiagnostic") == "ML-RUN-CHILD-EXIT" and outcome.cleanup_complete, record.get("dispatchDiagnostic")
    if case == "cancel-paused":  # the case fails unless it exercised the cancel path
        assert "cancelReturnedMonotonicNs" in record and "cancelNotIssued" not in record, record.get("cancelNotIssued", "no cancel return")
        assert "cancellerAliveAfterJoin" not in record, "entry.stop still running after the join"  # S1c finding 22, LOW-1
        assert record["cancelRequestedMonotonicNs"] < record["startReturnedMonotonicNs"], "cancel after the run returned"
        assert record.get("dispatchDiagnostic") == "ML-SCHEDULE-CANCELLED", record.get("dispatchDiagnostic")
        observed = [s for s in record["steps"] if s["step_id"].startswith("observe-")]
        assert observed and all(s["disposition"] == "completed" for s in observed), observed  # one path (MEDIUM-3)
        # the P3 closure facts, not only the path (S1c finding 20; writer end state per DR-2)
        assert record.get("persistenceFailure") is None, record.get("persistenceFailure")
        assert record.get("cleanupComplete") is True, record.get("closureDiagnostics")
        native = record.get("nativeUnits") or []
        assert len(native) == len(ORDER) and all(u.get("issued") and u.get("native_retired") and u.get("direct_child_reaped")
                                                 for u in native), native
        writers = [r.get("writer") or {} for r in record.get("closureTerminalReports") or []]
        assert writers and all(w.get("after_state") in ("failed", "closed") for w in writers), writers
