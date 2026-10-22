#!/bin/bash
# Lite CARLA closed-loop integration run (Phase 7; engineering integration, NOT AEB validation, NOT M1).
#
#   run-live.sh <case> [run-dir]      case: nominal | no-carla | cancel-paused | freeze-vcu
#
# Preconditions: a CARLA 0.9.15 server on 127.0.0.1:2000 (except case no-carla), a zenoh router on
# tcp/127.0.0.1:7447, and no other tick owner or actuator writer on that world (checked below).
set -u
CASE=${1:-nominal}
L10=/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0
RUN=${2:-$L10/.x-verse-build/runs/xverse-lite-live-20261022/lite-$(date +%Y%m%dT%H%M%S)-$CASE}
HERE=$(cd "$(dirname "$0")" && pwd)
export XVERSE_PLATFORM_SRC=${XVERSE_PLATFORM_SRC:-$L10/.x-verse-build/cache/xverse-lite-live-20261022/platform-src}
export XVERSE_COMPAT_SRC=${XVERSE_COMPAT_SRC:-/home/jefferson/xverse-compat-worktrees/phase7-live-20261022}
VENV=$L10/.x-verse-build/cache/xverse-lite-live-20261022/driver-venv
CARLA_ENV=$L10/.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310
SITE=$CARLA_ENV/lib/python3.10/site-packages
export XVERSE_LIVE_RUN_DIR=$RUN XVERSE_LIVE_CASE=$CASE
mkdir -p "$RUN/carla-home"
exec > >(tee "$RUN/run-live.log") 2>&1
echo "case=$CASE run=$RUN started=$(date -Is)"

# 1. Identities (hashes only; nothing is fetched).
{
  echo "blueprint $(git -C "$HERE" rev-parse HEAD) dirty=$(git -C "$HERE" status --porcelain | wc -l)"
  echo "compat $(git -C "$XVERSE_COMPAT_SRC" rev-parse HEAD) dirty=$(git -C "$XVERSE_COMPAT_SRC" status --porcelain | wc -l)"
  echo "platform-src $(cat "$XVERSE_PLATFORM_SRC/.export-revision" 2>/dev/null || echo unknown)"
  sha256sum /usr/bin/python3.10 /home/jefferson/.pyenv/versions/3.13.13/bin/python3.13 /usr/bin/zenohd \
    "$L10/.x-verse-build/cache/xverse-compat-wheels/carla-0.9.15-cp310-cp310-manylinux_2_27_x86_64.whl" \
    "$L10"/.x-verse-build/cache/xverse-lite-live-20261022/wheels/*.whl
  echo "legacy-vcu $(git -C /home/jefferson/autoverse/vecu/vcu_zenoh rev-parse HEAD) dirty=$(git -C /home/jefferson/autoverse/vecu/vcu_zenoh status --porcelain | wc -l)"
  sha256sum /home/jefferson/autoverse/vecu/vcu_zenoh/src/*.py
  cat /home/jefferson/carla-simulator/VERSION 2>/dev/null | head -1
} > "$RUN/identities.txt"

# 1b. Every unit module must compile on its interpreter (a unit that dies at import is invisible: /dev/null streams).
/usr/bin/python3.10 -B -c "import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]" "$XVERSE_COMPAT_SRC"/src/xverse_compat_carla/*.py \
  && /home/jefferson/.pyenv/versions/3.13.13/bin/python3.13 -B -c "import ast,sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]" \
     "$XVERSE_COMPAT_SRC"/src/xverse_compat/live/*.py "$XVERSE_COMPAT_SRC"/src/xverse_compat/carla_client.py \
  || { echo "BLOCKED: a unit module does not compile"; exit 4; }

# 2. Host state: no competing tick owner or actuator writer.
ps -eo pid=,comm=,args= | awk '$2 !~ /^(bash|sh|grep|ps|awk|timeout|tee)$/' | grep -E 'virtual_vehicle.py|automate.py|vehicle_manual_control.py|manual_control|automatic_control|run_autoverse.py|vcu_zenoh/src/main.py| main.py$' \
  > "$RUN/host-competing-processes.txt"
if [ -s "$RUN/host-competing-processes.txt" ]; then echo "BLOCKED: competing simulation clients running"; cat "$RUN/host-competing-processes.txt"; exit 4; fi
ss -tln | grep -q ':7447 ' || { echo "BLOCKED: no zenoh router on 7447"; exit 4; }
if [ "$CASE" != no-carla ]; then ss -tln | grep -q ':2000 ' || { echo "BLOCKED: no CARLA server on 2000"; exit 4; }; fi
ss -tlnp > "$RUN/listeners-before.txt" 2>/dev/null

# 3. Passive evaluation observer (never feeds runtime).
OBS=
if [ "$CASE" != no-carla ]; then
  (cd "$XVERSE_COMPAT_SRC/src" && exec env -i PATH=/usr/bin HOME="$RUN/carla-home" /usr/bin/python3.10 -s -B -m xverse_compat_carla.observe \
     --role xverse-lite-ego --duration-s 90 --out "$RUN/observer.jsonl" --carla-site "$SITE") 2> "$RUN/observer.err" &
  OBS=$!
fi

# 4. The Maestro run. Maestro's journal and Argus root live on tmpfs during the run (its persistence RPCs are
#    fsync-bound and loop10 is a loop-mounted image) and are copied into the evidence directory afterwards.
SHM=/dev/shm/xverse-lite-$(basename "$RUN")
(cd "$HERE" && env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 "$VENV/bin/python" -B -m pytest -q -p no:cacheprovider \
   --basetemp "$SHM" --rootdir "$HERE" test_live_closed_loop.py)
PYTEST=$?
echo "maestro-harness exit=$PYTEST"
cp -a "$SHM" "$RUN/maestro-tmp" && rm -rf "$SHM"

# 5. Cleanup: observer, restore guard, residue checks.
[ -n "$OBS" ] && { kill -TERM "$OBS" 2>/dev/null; wait "$OBS"; echo "observer exit=$?"; }
if [ "$CASE" != no-carla ]; then
  (cd "$XVERSE_COMPAT_SRC/src" && env -i PATH=/usr/bin HOME="$RUN/carla-home" /usr/bin/python3.10 -s -B -m xverse_compat_carla.restore --carla-site "$SITE") > "$RUN/restore-guard.json"
  echo "restore-guard exit=$? $(cat "$RUN/restore-guard.json")"
fi
ps -eo pid=,comm=,args= | awk '$2 !~ /^(bash|sh|grep|ps|awk|timeout|tee)$/' | grep -E 'xverse_compat_carla.main|xverse_compat.live|-B main.py' > "$RUN/residue-processes.txt"
echo "residue processes: $(wc -l < "$RUN/residue-processes.txt")"
SOCK=/run/user/$(id -u)/xverse-lite/lite-carla-closed-loop.sock
if [ -S "$SOCK" ]; then rm -f "$SOCK"; echo "removed the run's leftover socket $SOCK (owner killed by Maestro)" | tee "$RUN/socket-cleanup.txt"; fi
ls /run/user/$(id -u)/xverse-lite/ > "$RUN/residue-sockets.txt" 2>/dev/null; echo "residue sockets: $(wc -l < "$RUN/residue-sockets.txt")"
ss -tlnp > "$RUN/listeners-after.txt" 2>/dev/null
echo "ended=$(date -Is)"
exit $PYTEST
