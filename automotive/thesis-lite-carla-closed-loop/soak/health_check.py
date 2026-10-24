"""Independent, read-only CARLA server health check for the S1d soak (thesis 029 plan.md, Soak, "CARLA").

    env -i PATH=/usr/bin HOME=<writable dir> /usr/bin/python3.10 -s -B health_check.py --carla-site <site-packages>

(libcarla aborts without HOME; the runner treats every non-zero exit, an abort included, as unhealthy.)

A fresh client calls ``get_world()`` within 15 s. In an asynchronous world it then waits passively for a frame
(``wait_for_tick(5 s)``). In a synchronous world (a freshly started server on this host is synchronous at 0.05 s with
no tick owner; S1c finding 57, thesis DR-21) no frame comes unless someone ticks, so the check only requires the
server to answer its server requests ``get_world``, ``get_settings`` and ``get_map`` within the 15 s client timeout
(``tickProbe: skipped-synchronous``). The actor count and ``get_snapshot()`` come from the client's local view in a
world nobody has ticked; they are recorded (``localSnapshotFrame``) but are not evidence (finding 58, MEDIUM-1). It
never ticks, never changes settings and never spawns or destroys actors, so it is not an owner. It is run outside the
run window: before the preflight and at the end of the cleanup. A failure is the objective, predeclared evidence that
makes a run INVALID (an external dependency failure); a synchronous world after the cleanup is a restore failure
(FAIL) in the runner's ``classify`` whatever this check reports (DR-21). Prints one JSON object; exit 0 healthy, 1
unhealthy.
"""

import argparse
import json
import site
import sys
import time


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--carla-site", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    args = parser.parse_args(argv)
    site.addsitedir(args.carla_site)
    result = {"check": "carla-health", "host": args.host, "port": args.port, "startedMonotonicNs": time.monotonic_ns()}
    try:
        import carla  # noqa: PLC0415

        client = carla.Client(args.host, args.port)
        client.set_timeout(15.0)
        world = client.get_world()
        result["getWorldS"] = round((time.monotonic_ns() - result["startedMonotonicNs"]) / 1e9, 3)
        settings = world.get_settings()
        result["synchronousMode"] = bool(settings.synchronous_mode)
        result["map"] = world.get_map().name
        result["vehicles"] = len(world.get_actors().filter("vehicle.*"))
        began = time.monotonic_ns()
        if result["synchronousMode"]:  # DR-21: never tick; the server requests above are the evidence
            result["localSnapshotFrame"] = int(world.get_snapshot().frame)  # client-local, not evidence (finding 58)
            result["tickProbe"] = "skipped-synchronous"
        else:
            snapshot = world.wait_for_tick(5.0)  # passive: waits for a frame another party (the server) produces
            result["tickProbe"] = "wait-for-tick"
            result["waitForTickS"] = round((time.monotonic_ns() - began) / 1e9, 3)
            result["frame"] = int(snapshot.frame)
        result["healthy"] = True
    except Exception as error:  # any failure is the INVALID evidence, recorded verbatim
        result["healthy"] = False
        result["error"] = f"{type(error).__name__}: {error}"
    result["endedMonotonicNs"] = time.monotonic_ns()
    print(json.dumps(result, sort_keys=True))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    sys.exit(main())
