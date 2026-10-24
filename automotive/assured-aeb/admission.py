"""Harness fault-admission path of the assured AEB blueprint (WP-10 increment #1; review-wp10-admission finding 1).

``admit_run`` runs the admission order of thesis design ``wp10-fault-relay.md`` §5 (decisions.md "WP-10 fault relay"):

1. generate the arm's documents (topology form for the fault rule, Maestro form for the plan);
2. validate the FreezeBound inputs;
3. check simulation-time freeze durations: ``D / step_s * max_step_host_s + 2 * handshake_s <= thaw_bound_s``,
   refusing while the D-4c measurements are unknown;
4. ``check_fault_admission``, then the interim gate: no fault is admitted until option (A) is on the platform;
5. prepare the Maestro plan;
6. ``admit_schedule``.

The first refusing stage stops the run: no later stage is called. Offline engineering code; it authorizes no run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable

import check_topology as C
import topology as T

STAGES = ("generate", "bound-inputs", "sim-duration", "fault-admission", "prepare", "admit-schedule")
TIME_UNITS_NS = {"ns": 1, "us": 1_000, "ms": 1_000_000, "s": 1_000_000_000}
SIM_DOMAIN = "carla-simulation"
INTERIM = "WP-10 interim: option (A) is not on the platform; no fault is admitted (decisions.md \"WP-10 fault relay\")"


def _positive(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


@dataclass(frozen=True)
class SimTimeFreezeBound:
    """Inputs of the WP-10 §4 inequality. ``None`` means unknown: ``max_step_host_s`` and ``handshake_s`` are
    ``TODO: measurement`` (D-4c); ``step_s`` is the fixed step (K-10); ``thaw_bound_s`` comes from the admitted
    schedule (``cadence - health_scan_seconds``). None is a protocol value; none is defaulted."""

    thaw_bound_s: float | None
    step_s: float | None
    max_step_host_s: float | None
    handshake_s: float | None

    def problems(self) -> list[str]:
        return [f"{name} must be a known finite number > 0 (got {getattr(self, name)!r})"
                for name in ("thaw_bound_s", "step_s", "max_step_host_s", "handshake_s") if not _positive(getattr(self, name))]

    def host_seconds(self, duration_ns: int) -> float:
        """Host time from apply to clear: ``D / step`` steps at the maximum step time, plus two handshakes."""

        return duration_ns / 1e9 / self.step_s * self.max_step_host_s + 2 * self.handshake_s


def sim_duration_ns(fault: dict[str, Any]) -> int | None:
    """The declared duration of a fault in simulation-time ns, or ``None`` if it is not simulation-time keyed."""

    intent = fault.get("extensions", {}).get(T.EXPERIMENT, {})
    duration, domain = intent.get("duration", {}), intent.get("timeDomainId")
    unit, value = duration.get("unit"), duration.get("value")
    if domain != SIM_DOMAIN or unit not in TIME_UNITS_NS or type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    return round(value * TIME_UNITS_NS[unit])


def option_a_available(platform: Any = None) -> bool:
    """The interim-gate switch: the platform declares simulation-time fault triggers (option (A), increment #3).

    The probe is ``xverse.faults.SIMULATION_TIME_TRIGGERS is True``; increment #3 provides it or changes this probe
    in its ADR. ``platform`` may be passed by a test to stand in for the module.
    """

    if platform is None:
        try:
            import xverse.faults as platform  # noqa: PLC0415
        except ImportError:
            return False
    return getattr(platform, "SIMULATION_TIME_TRIGGERS", False) is True


@dataclass
class AdmissionResult:
    admitted: bool
    stage: str
    refusals: list[str]
    stages_run: list[str] = field(default_factory=list)
    schedule: Any = None


def _compile_and_prepare(docs: dict[str, dict[str, Any]], schema_paths: tuple[str, ...]):
    validation, result = C.compile_docs(docs, schema_paths)
    if result is None or not result.is_valid:
        raise ValueError(f"plan does not compile: {C._diag(validation.diagnostics if result is None else result.diagnostics)}")
    return C.prepare(validation, result)


def admit_run(arm: str, faults: list[dict[str, Any]], *, freeze_bound: "C.FreezeBound | None",
              sim_bound: SimTimeFreezeBound | None, op: float, schema_paths: tuple[str, ...], platform: Any = None,
              prepare_fn: Callable[..., Any] | None = None,
              admit_fn: Callable[..., Any] | None = None) -> AdmissionResult:
    """Run the WP-10 §5 admission order for ``arm`` with ``faults``; stop at the first refusal."""

    prepare_fn = prepare_fn or _compile_and_prepare
    admit_fn = admit_fn or C.admit
    run: list[str] = []

    def refuse(stage: str, refusals: list[str]) -> AdmissionResult:
        return AdmissionResult(False, stage, refusals, run)

    run.append("generate")
    pins = T.read_pins()
    topology_docs = T.documents(arm, pins, form="topology", faults=faults)
    maestro_docs = T.documents(arm, pins, form="maestro", faults=[f for f in faults if f["faultKind"] == "freeze"])
    freezes = [f for f in faults if f["faultKind"] == "freeze"]
    if faults:
        run.append("bound-inputs")
        if freezes and type(freeze_bound) is not C.FreezeBound:
            return refuse("bound-inputs", ["a freeze needs a validated FreezeBound (thaw_bound_s, max_cycle_s > 0)"])
        if freezes and sim_bound is None:
            return refuse("bound-inputs", ["a freeze needs the simulation-time FreezeBound inputs (WP-10 §4)"])
        run.append("sim-duration")
        problems = []
        if freezes:
            problems = list(sim_bound.problems())
            if problems:
                return refuse("sim-duration", [f"simulation-time freeze bound unknown or invalid: {p}" for p in problems])
            for fault in freezes:
                duration = sim_duration_ns(fault)
                if duration is None:
                    problems.append(f"{fault['id']}: freeze duration is not keyed to simulation time ({SIM_DOMAIN}); PAIR-1 needs it")
                elif sim_bound.host_seconds(duration) > sim_bound.thaw_bound_s:
                    problems.append(f"{fault['id']}: {duration} ns needs {sim_bound.host_seconds(duration):.3f} s of host time, above "
                                    f"the thaw bound {sim_bound.thaw_bound_s} s")
            if problems:
                return refuse("sim-duration", problems)
        run.append("fault-admission")
        refusals = C.check_fault_admission(topology_docs, faults)
        if refusals:
            return refuse("fault-admission", refusals)
        if not option_a_available(platform):
            return refuse("fault-admission", [INTERIM])
    run.append("prepare")
    prepared = prepare_fn(maestro_docs, schema_paths)
    run.append("admit-schedule")
    schedule = admit_fn(prepared, op)
    return AdmissionResult(True, "admit-schedule", [], run, schedule)


# --------------------------------------------------------------------------------------------------
# The hub's re-check when it arms (interface stub for increment #4)
# --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ArmDescriptor:
    """The minimum descriptor the dispatcher sends to the hub at ``arm`` (design §3)."""

    entry_id: str
    target_element: str
    kind: str
    onset_ns: int
    duration_ns: int
    parameters: tuple = ()


class HubArmingRecheck:
    """The hub's second line: it repeats the target and kind rule for each descriptor before arming it."""

    def __init__(self, topology_docs: dict[str, dict[str, Any]]) -> None:
        self.docs = topology_docs

    def recheck(self, descriptor: ArmDescriptor) -> list[str]:
        ext = self.docs["system.json"]["extensions"][T.EXT]
        flows = {f["id"]: f for f in self.docs["system.json"]["spec"].get("flows", [])}
        freeze = ext["freezeTargets"]
        if descriptor.kind == "freeze":
            allowed = set(freeze["admitted"]) | {u for group in freeze["admittedSets"] for u in group}
            return [] if descriptor.target_element in allowed else [f"{descriptor.entry_id}: freeze of {descriptor.target_element} not armable"]
        if descriptor.target_element in flows:
            admitted = flows[descriptor.target_element].get("extensions", {}).get(T.EXT, {}).get("faultAdmission", [])
            if descriptor.kind in admitted:
                return []
        return [f"{descriptor.entry_id}: {descriptor.kind} on {descriptor.target_element} not armable (decisions.md §K)"]

    def arm(self, descriptor: ArmDescriptor) -> None:
        raise NotImplementedError("WP-10 increment #4: the hub relay and its control channel are not implemented yet")
