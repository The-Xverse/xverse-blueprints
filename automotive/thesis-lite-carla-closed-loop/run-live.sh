#!/bin/bash
# Lite CARLA closed-loop integration run (Phase 7; engineering integration, NOT AEB validation, NOT M1).
#
#   run-live.sh <case> [run-dir]      case: nominal | no-carla | cancel-paused | freeze-vcu
#
# Preconditions: CARLA 0.9.15 on 127.0.0.1:2000 (except no-carla), a zenoh router on tcp/127.0.0.1:7447, no other
# tick owner or actuator writer (checked: process names and established CARLA connections), clean candidate trees.
set -u
CASE=${1:-nominal}
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/lib-live.sh"
RUN=${2:-$L10/.x-verse-build/runs/xverse-lite-live-20261022/lite-$(date +%Y%m%dT%H%M%S)-$CASE}
export XVERSE_PLATFORM_SRC=${XVERSE_PLATFORM_SRC:-$L10/.x-verse-build/cache/xverse-lite-live-20261022/platform-src}
require_compat || exit 4
export XVERSE_COMPAT_SRC
export XVERSE_LIVE_RUN_DIR=$RUN XVERSE_LIVE_CASE=$CASE
mkdir -p "$RUN/carla-home"
exec > >(trap '' INT TERM; exec tee "$RUN/run-live.log") 2>&1  # the log survives a Ctrl-C of the group (S1c finding 7)
echo "case=$CASE run=$RUN started=$(date -Is) wall_epoch_ns=$(date +%s%N)"
OBS=; PYTEST=1; SHM=/dev/shm/xverse-lite-$(basename "$RUN"); SOCK=/run/user/$(id -u)/xverse-lite/lite-carla-closed-loop.sock

cleanup() {  # runs on every exit path, including an interrupt (review 1 R-7); always ends the script (S1c finding 9)
  local rc=$?
  trap - EXIT; trap '' INT TERM PIPE  # a second signal or a closed log must not cut the guard short (S1c finding 7)
  ps -eo pid=,comm=,args= | awk '$2 !~ /^(bash|sh|grep|ps|awk|timeout|tee)$/' | grep -E 'xverse_compat_carla.main|xverse_compat.live|-B main.py' > "$RUN/residue-processes.txt"
  echo "residue processes: $(wc -l < "$RUN/residue-processes.txt")"
  if [ "$CASE" != no-carla ] && [ -s "$RUN/world-before.json" ]; then  # residue first, then the guard (skipped after a BLOCKED preflight, review 2 N-5)
    (cd "$XVERSE_COMPAT_SRC/src" && env -i PATH=/usr/bin HOME="$RUN/carla-home" /usr/bin/python3.10 -s -B -m xverse_compat_carla.restore \
       --carla-site "$SITE" --settings-from "$RUN/world-before.json" --owned-registry "$RUN/owned-actors.json") > "$RUN/restore-guard.json"
    echo "restore-guard exit=$? $(cat "$RUN/restore-guard.json")"
    sleep 1
  fi
  [ -n "$OBS" ] && { kill -TERM "$OBS" 2>/dev/null; wait "$OBS"; echo "observer exit=$?"; }
  if [ -S "$SOCK" ]; then rm -f "$SOCK"; echo "removed the run's leftover socket $SOCK (owner killed by Maestro)" | tee "$RUN/socket-cleanup.txt"; fi
  ls /run/user/$(id -u)/xverse-lite/ > "$RUN/residue-sockets.txt" 2>/dev/null; echo "residue sockets: $(wc -l < "$RUN/residue-sockets.txt")"
  [ -d "$SHM" ] && cp -a "$SHM" "$RUN/maestro-tmp" && rm -rf "$SHM"
  [ "$CASE" != no-carla ] && carla_clients "$RUN/carla-clients-after.txt"
  ss -tlnp > "$RUN/listeners-after.txt" 2>/dev/null
  echo "ended=$(date -Is) maestro-harness exit=$PYTEST script exit=$rc"
}
trap cleanup EXIT
trap 'exit 130' INT   # a signal ends the script through the EXIT trap; it never resumes the run (S1c finding 9)
trap 'exit 143' TERM

# 1. Identities and revisions (hashes only; nothing is fetched).
record_revisions "$RUN" "blueprint=$HERE" "compat=$XVERSE_COMPAT_SRC" || exit 4
{
  echo "compat-src $XVERSE_COMPAT_SRC"  # the checkout actually used (S1 FR-014)
  echo "platform-src $(cat "$XVERSE_PLATFORM_SRC/.export-revision" 2>/dev/null || echo unknown)"
  sha256sum /usr/bin/python3.10 /home/jefferson/.pyenv/versions/3.13.13/bin/python3.13 /usr/bin/zenohd \
    "$L10/.x-verse-build/cache/xverse-compat-wheels/carla-0.9.15-cp310-cp310-manylinux_2_27_x86_64.whl" \
    "$L10"/.x-verse-build/cache/xverse-lite-live-20261022/wheels/*.whl
  legacy_identity legacy-vcu /home/jefferson/autoverse/vecu/vcu_zenoh
  sha256sum /home/jefferson/autoverse/vecu/vcu_zenoh/src/*.py
  cat /home/jefferson/carla-simulator/VERSION 2>/dev/null | head -1
} >> "$RUN/identities.txt"

# 1b. Every unit module must compile (a unit that dies at import is invisible: /dev/null streams).
/usr/bin/python3.10 -B -c "import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]" "$XVERSE_COMPAT_SRC"/src/xverse_compat_carla/*.py \
  && /home/jefferson/.pyenv/versions/3.13.13/bin/python3.13 -B -c "import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]" \
     "$XVERSE_COMPAT_SRC"/src/xverse_compat/live/*.py "$XVERSE_COMPAT_SRC"/src/xverse_compat/carla_client.py \
  || { echo "BLOCKED: a unit module does not compile"; exit 4; }

# 2. Host state: no competing tick owner or actuator writer (process names and established connections).
ps -eo pid=,comm=,args= | awk '$2 !~ /^(bash|sh|grep|ps|awk|timeout|tee)$/' | grep -E 'virtual_vehicle.py|automate.py|vehicle_manual_control.py|manual_control|automatic_control|run_autoverse.py|vcu_zenoh/src/main.py| main.py$' \
  > "$RUN/host-competing-processes.txt"
if [ -s "$RUN/host-competing-processes.txt" ]; then echo "BLOCKED: competing simulation clients running"; cat "$RUN/host-competing-processes.txt"; exit 4; fi
ss -tln | grep -q ':7447 ' || { echo "BLOCKED: no zenoh router on 7447"; exit 4; }
if [ "$CASE" != no-carla ]; then
  ss -tln | grep -q ':2000 ' || { echo "BLOCKED: no CARLA server on 2000"; exit 4; }
  carla_clients "$RUN/carla-clients-before.txt" || { echo "BLOCKED: unexpected client connected to CARLA"; cat "$RUN/carla-clients-before.txt"; exit 4; }
  world_settings "$RUN/world-before.json" "$RUN/carla-home" || { echo "BLOCKED: cannot read the world settings"; exit 4; }
  echo "world before: $(cat "$RUN/world-before.json")"
  python3 -c "import json,sys; sys.exit(1 if json.load(open(sys.argv[1])).get('vehicles') else 0)" "$RUN/world-before.json" \
    || { echo "BLOCKED: the declared scenario needs a world without vehicles (review log 22)"; rm -f "$RUN/world-before.json"; exit 4; }
fi
ss -tlnp > "$RUN/listeners-before.txt" 2>/dev/null

# 3. Passive evaluation observer (never feeds runtime); it keeps running through the restore guard.
if [ "$CASE" != no-carla ]; then
  (cd "$XVERSE_COMPAT_SRC/src" && exec env -i PATH=/usr/bin HOME="$RUN/carla-home" /usr/bin/python3.10 -s -B -m xverse_compat_carla.observe \
     --role xverse-lite-ego --duration-s 120 --out "$RUN/observer.jsonl" --carla-site "$SITE") 2> "$RUN/observer.err" &
  OBS=$!
fi

# 4. The Maestro run. Maestro's journal and Argus root live on tmpfs during the run (fsync-bound persistence
#    RPCs; loop10 is a loop-mounted image) and are copied into the evidence directory by cleanup().
(cd "$HERE" && env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 "$VENV/bin/python" -B -m pytest -q -p no:cacheprovider \
   --basetemp "$SHM" --rootdir "$HERE" test_live_closed_loop.py)
PYTEST=$?
exit $PYTEST
