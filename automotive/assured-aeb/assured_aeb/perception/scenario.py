"""Verified live-scenario placement for the offline dataset (WP-09 #1; review-wp09-labels findings 3-4, MEDIUM-2, LOW-1).

The scenario file's bytes are verified against the declared ``scenarioSha256`` before anything is read from them. The
target placement is then derived from the verified record: ``none``, ``ego-lane`` or ``adjacent-lane`` with ``side``
and ``direction``. This mirrors the placement members of compat ``xverse_compat_carla/scenario.py`` ``target_of``
(schemas 1 and 2; WP-02b ``adjacentLane``). Compat's full validation still runs at spawn, and nothing here imports
compat.

The refusal of adjacent-lane targets in evaluation runs is not done here. It belongs to evaluation-run admission
(WP-10 #5 / WP-16; decisions.md "WP-09 data separation" (1)).

The ``map`` returned here is the scenario's *declared* map. Binding it to the loaded world is an obligation of
increment #6 (review-wp09-labels finding 6 LOW-3; decisions.md "WP-09 data separation, amendment 1"): the map comes
from the evaluation-only observer header (``world.get_map().name``), its comparison with ``Town10HD_Opt`` is
``TODO: engineering verification``, and a schema-1 scenario's stray ``map`` member is refused there.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA_1 = "xverse-compat.carla-live-scenario/1"
SCHEMA_2 = "xverse-compat.carla-live-scenario/2"
ADJACENT_MEMBERS = {"side", "direction"}
ADJACENT_SIDES = ("left", "right")
ADJACENT_DIRECTIONS = ("same", "opposite")
PLACEMENTS = ("none", "ego-lane", "adjacent-lane")


def verified_scenario(data: bytes, scenario_sha256: str) -> dict[str, Any]:
    """Verify the bytes against the digest; return ``{spawnPointIndex, map, targetPlacement}`` (fail-closed)."""

    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("the scenario must be given as the file's bytes")
    if hashlib.sha256(data).hexdigest() != scenario_sha256:
        raise ValueError("the scenario file does not match its scenarioSha256")
    scenario = json.loads(bytes(data).decode("utf-8"))
    if not isinstance(scenario, dict):
        raise ValueError("the live scenario must be a JSON object")
    schema = scenario.get("schema", SCHEMA_1)
    if schema not in (SCHEMA_1, SCHEMA_2):
        raise ValueError(f"unknown live-scenario schema {schema!r}")
    if type(scenario.get("spawnPointIndex")) is not int or scenario["spawnPointIndex"] < 0:
        raise ValueError("spawnPointIndex must be a non-negative int")
    if schema == SCHEMA_1:
        if "target" in scenario:
            raise ValueError(f"a target needs schema {SCHEMA_2}")
        placement: dict[str, Any] = {"kind": "none"}
    else:
        if not isinstance(scenario.get("map"), str) or not scenario["map"]:
            raise ValueError("map must be a non-empty string")
        target = scenario.get("target")
        if target is None and "target" not in scenario:
            placement = {"kind": "none"}
        elif not isinstance(target, dict):
            raise ValueError("target must be an object (omit it for no target)")
        elif "adjacentLane" not in target:
            placement = {"kind": "ego-lane"}
        else:
            adjacent = target["adjacentLane"]
            if not isinstance(adjacent, dict) or set(adjacent) != ADJACENT_MEMBERS:
                raise ValueError(f"target adjacentLane must be exactly {sorted(ADJACENT_MEMBERS)}")
            if adjacent["side"] not in ADJACENT_SIDES or adjacent["direction"] not in ADJACENT_DIRECTIONS:
                raise ValueError(f"adjacentLane side must be one of {ADJACENT_SIDES} and direction one of {ADJACENT_DIRECTIONS}")
            placement = {"kind": "adjacent-lane", "side": adjacent["side"], "direction": adjacent["direction"]}
    return {"spawnPointIndex": scenario["spawnPointIndex"], "map": scenario.get("map"), "targetPlacement": placement}


def check_placement(placement: Any) -> bool:
    """True when ``placement`` is a well-formed target-placement record."""

    if not isinstance(placement, dict) or placement.get("kind") not in PLACEMENTS:
        return False
    if placement["kind"] == "adjacent-lane":
        return set(placement) == {"kind"} | ADJACENT_MEMBERS and placement["side"] in ADJACENT_SIDES \
            and placement["direction"] in ADJACENT_DIRECTIONS
    return set(placement) == {"kind"}
