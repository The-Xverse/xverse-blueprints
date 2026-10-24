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

Repairs of review finding 3 (finding 4): every fault's trigger and duration must be keyed to simulation time
(PAIR-1); the inequality counts whole simulator steps, ``ceil(D / step_s)``; the FreezeBound tick cap is applied
(each simulator step counts as at least one dispatcher cycle under the lockstep hub, a conservative reading); the hub
re-check applies the CC-1 rule over the armed batch and repeats the duration bound.

Test seams: ``platform``, ``prepare_fn`` and ``admit_fn`` exist for the tests only. The increment #5 run command must
not pass them; the real harness uses the imported ``xverse.faults`` module and the real prepare and admit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Iterable

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

    def steps(self, duration_ns: int) -> int:
        """Whole simulator steps held by a freeze of ``duration_ns``: ``ceil(D / step)`` (AD-30 delivery rule)."""

        return math.ceil(duration_ns / 1e9 / self.step_s - 1e-12)

    def host_seconds(self, duration_ns: int) -> float:
        """Host time from apply to clear: ``ceil(D / step)`` steps at the maximum step time, plus two handshakes."""

        return self.steps(duration_ns) * self.max_step_host_s + 2 * self.handshake_s


def _ns(value: Any, unit: Any) -> int | None:
    if unit not in TIME_UNITS_NS or type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        return None
    return round(value * TIME_UNITS_NS[unit])


def sim_keying(fault: dict[str, Any]) -> tuple[int, int] | None:
    """``(onset_ns, duration_ns)`` of a fault whose time trigger and duration are both in simulation time, else ``None``
    (review finding 3, MEDIUM-1: every fault, message faults included)."""

    intent = fault.get("extensions", {}).get(T.EXPERIMENT, {})
    trigger, duration = intent.get("trigger", {}), intent.get("duration", {})
    if intent.get("timeDomainId") != SIM_DOMAIN or trigger.get("kind") != "time":
        return None
    onset, length = _ns(trigger.get("at"), trigger.get("unit")), _ns(duration.get("value"), duration.get("unit"))
    return None if onset is None or length is None else (onset, length)


def sim_duration_ns(fault: dict[str, Any]) -> int | None:
    """The declared duration of a simulation-time-keyed fault in ns, or ``None``."""

    keying = sim_keying(fault)
    return None if keying is None else keying[1]


def freeze_duration_problems(entry_id: str, duration_ns: int, sim_bound: SimTimeFreezeBound,
                             freeze_bound: "C.FreezeBound | None" = None) -> list[str]:
    """The duration rules for one freeze: the WP-10 §4 inequality in whole steps, and the FreezeBound tick cap."""

    problems = []
    steps = sim_bound.steps(duration_ns)
    if sim_bound.host_seconds(duration_ns) > sim_bound.thaw_bound_s:
        problems.append(f"{entry_id}: {duration_ns} ns = {steps} steps needs {sim_bound.host_seconds(duration_ns):.3f} s of host "
                        f"time, above the thaw bound {sim_bound.thaw_bound_s} s")
    if freeze_bound is not None and steps > freeze_bound.max_ticks:
        problems.append(f"{entry_id}: {steps} steps exceed the FreezeBound tick cap {freeze_bound.max_ticks} "
                        f"({freeze_bound.thaw_bound_s} s / {freeze_bound.max_cycle_s} s per tick)")
    return problems


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
        problems = [f"{f['id']}: trigger and duration must both be keyed to simulation time ({SIM_DOMAIN}); PAIR-1 needs it"
                    for f in faults if sim_keying(f) is None]
        if problems:
            return refuse("sim-duration", problems)
        if freezes:
            problems = list(sim_bound.problems())
            if problems:
                return refuse("sim-duration", [f"simulation-time freeze bound unknown or invalid: {p}" for p in problems])
            for fault in freezes:
                problems += freeze_duration_problems(fault["id"], sim_duration_ns(fault), sim_bound, freeze_bound)
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
    """The hub's second line: before arming, it repeats the target and kind rule, the CC-1 set rule over the whole
    armed batch, and (when given) the duration bound (review finding 3, MEDIUM-3 and LOW-3)."""

    def __init__(self, topology_docs: dict[str, dict[str, Any]], sim_bound: SimTimeFreezeBound | None = None,
                 freeze_bound: "C.FreezeBound | None" = None) -> None:
        self.docs, self.sim_bound, self.freeze_bound = topology_docs, sim_bound, freeze_bound

    def recheck(self, batch: Iterable[ArmDescriptor]) -> list[str]:
        """Re-check one armed batch; empty means every descriptor is armable."""

        batch = list(batch)
        ext = self.docs["system.json"]["extensions"][T.EXT]
        flows = {f["id"]: f for f in self.docs["system.json"]["spec"].get("flows", [])}
        freeze = ext["freezeTargets"]
        single, sets = set(freeze["admitted"]), [tuple(g) for g in freeze["admittedSets"]]
        freezes = [d for d in batch if d.kind == "freeze"]
        refusals = []
        for d in batch:
            if d.kind == "freeze":
                if d.target_element in single:
                    pass
                elif any(d.target_element in group for group in sets):
                    complete = any(d.target_element in group and all(
                        any(o.target_element == member and (o.onset_ns, o.duration_ns) == (d.onset_ns, d.duration_ns) for o in freezes)
                        for member in group) for group in sets)
                    if not complete:
                        refusals.append(f"{d.entry_id}: freeze of {d.target_element} not armable alone (CC-1: every member, "
                                        "same onset and duration)")
                else:
                    refusals.append(f"{d.entry_id}: freeze of {d.target_element} not armable")
                if self.sim_bound is not None and not self.sim_bound.problems():
                    refusals += freeze_duration_problems(d.entry_id, d.duration_ns, self.sim_bound, self.freeze_bound)
                elif self.sim_bound is not None:
                    refusals.append(f"{d.entry_id}: duration bound unknown ({'; '.join(self.sim_bound.problems())})")
                continue
            if d.target_element in flows:
                admitted = flows[d.target_element].get("extensions", {}).get(T.EXT, {}).get("faultAdmission", [])
                if d.kind in admitted:
                    continue
            refusals.append(f"{d.entry_id}: {d.kind} on {d.target_element} not armable (decisions.md §K)")
        return refusals

    def arm(self, descriptor: ArmDescriptor) -> None:
        raise NotImplementedError("WP-10 increment #4: the hub relay and its control channel are not implemented yet")
