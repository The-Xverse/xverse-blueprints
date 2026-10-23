#!/bin/bash
# Baseline reference invocation (Phase 7): the legacy asynchronous vehicle loop with comparable components.
#
#   run-baseline.sh [run-dir]
#
# Components as in the author's run_autoverse.py steps 2 and 6 (VCU; virtual_vehicle.py via the
# run-virtual-vehicle-on-cloud recipe's final command, headless), on the same CARLA server and zenoh
# router. The human at vehicle_manual_control.py is replaced by the same declared stimulus used in the Lite
# run. Declared differences: no S-CORE, SOME/IP bridge or Android (not on the vehicle actuation path); the
# legacy vehicle chooses a random spawn point (recorded by the observer); the world stays asynchronous.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/lib-live.sh"
RUN=${1:-$L10/.x-verse-build/runs/xverse-lite-live-20261022/baseline-$(date +%Y%m%dT%H%M%S)}
COMPAT=${XVERSE_COMPAT_SRC:-/home/jefferson/xverse-compat-worktrees/phase7-live-20261022}
EX=/home/jefferson/carla-api/PythonAPI/examples
mkdir -p "$RUN/carla-home"
exec > >(tee "$RUN/run-baseline.log") 2>&1
echo "baseline run=$RUN started=$(date -Is)"
{
  echo "bridge-repo $(git -C /home/jefferson/autoverse/bridges/carla rev-parse HEAD) dirty=$(git -C /home/jefferson/autoverse/bridges/carla status --porcelain | wc -l)"
  sha256sum /home/jefferson/autoverse/bridges/carla/examples/virtual_vehicle.py $EX/virtual_vehicle.py \
    /home/jefferson/autoverse/bridges/carla/examples/signals_config.json $EX/signals_config.json
  echo "legacy-vcu $(git -C /home/jefferson/autoverse/vecu/vcu_zenoh rev-parse HEAD)"; sha256sum /home/jefferson/autoverse/vecu/vcu_zenoh/src/*.py
} > "$RUN/identities.txt"
record_revisions "$RUN" "blueprint=$HERE" "compat=$COMPAT" || exit 4
ps -eo pid=,comm=,args= | awk '$2 !~ /^(bash|sh|grep|ps|awk|timeout|tee)$/' | grep -E 'virtual_vehicle.py|automate.py|vehicle_manual_control.py|xverse_compat_carla.main|xverse_compat.live|vcu_zenoh/src/main.py| main.py$' > "$RUN/host-competing-processes.txt"
if [ -s "$RUN/host-competing-processes.txt" ]; then echo "BLOCKED: competing clients"; cat "$RUN/host-competing-processes.txt"; exit 4; fi
ss -tln | grep -q ':7447 ' && ss -tln | grep -q ':2000 ' || { echo "BLOCKED: router or CARLA missing"; exit 4; }
carla_clients "$RUN/carla-clients-before.txt" || { echo "BLOCKED: unexpected client connected to CARLA"; cat "$RUN/carla-clients-before.txt"; exit 4; }
world_settings "$RUN/world-before.json" "$RUN/carla-home"; echo "world before: $(cat "$RUN/world-before.json")"

(cd "$COMPAT/src" && exec env -i PATH=/usr/bin HOME="$RUN/carla-home" /usr/bin/python3.10 -s -B -m xverse_compat_carla.observe \
   --role ego_vehicle --duration-s 60 --out "$RUN/observer.jsonl" --carla-site "$SITE") 2> "$RUN/observer.err" & OBS=$!
(cd /home/jefferson/autoverse/vecu/vcu_zenoh/src && exec /usr/bin/python3 -B main.py) > "$RUN/vcu.out" 2> "$RUN/vcu.err" & VCU=$!
sleep 1
(cd /home/jefferson/autoverse/bridges/carla/examples && exec /usr/bin/python3 -B $EX/virtual_vehicle.py --host 127.0.0.1 --port 2000 \
   --router 127.0.0.1 --res 1280x960 --filter vehicle.audi.etron --rolename ego_vehicle --signals-config $EX/signals_config.json) \
   > "$RUN/virtual-vehicle.out" 2> "$RUN/virtual-vehicle.err" & VV=$!
# same declared stimulus and time base (host-monotonic from the first clock sample, DLG-12) as the Lite run
env -u PYTHONPATH PYTHONPATH="$COMPAT/src" "$VENV/bin/python" -B -m xverse_compat.live.stimulus --time-base wall --out "$RUN/stimulus.jsonl" 2> "$RUN/stimulus.err" & STIM=$!
wait $STIM; echo "stimulus exit=$?"
sleep 2
for P in $VV $VCU; do kill -INT $P 2>/dev/null; done   # as the author's supervisor: SIGINT first
for i in $(seq 1 20); do kill -0 $VV 2>/dev/null || kill -0 $VCU 2>/dev/null || break; sleep 0.5; done
for P in $VV $VCU; do kill -0 $P 2>/dev/null && { echo "terminating $P"; kill -TERM $P; }; done
wait $VV; echo "virtual-vehicle exit=$?"; wait $VCU; echo "vcu exit=$?"
kill -TERM $OBS 2>/dev/null; wait $OBS; echo "observer exit=$?"
(cd "$COMPAT/src" && env -i PATH=/usr/bin HOME="$RUN/carla-home" /usr/bin/python3.10 -s -B -c "
import sys,json,site; site.addsitedir('$SITE'); import carla
w=carla.Client('127.0.0.1',2000); w.set_timeout(10); w=w.get_world(); s=w.get_settings()
print(json.dumps({'synchronousMode': s.synchronous_mode, 'vehicles': [(a.id, a.type_id, a.attributes.get('role_name')) for a in w.get_actors().filter('vehicle.*')]}))") > "$RUN/world-after.json"
echo "world after: $(cat "$RUN/world-after.json")"
ps -eo pid=,comm=,args= | awk '$2 !~ /^(bash|sh|grep|ps|awk|timeout|tee)$/' | grep -E 'virtual_vehicle.py|vcu_zenoh|-B main.py|xverse_compat' > "$RUN/residue-processes.txt"
echo "residue processes: $(wc -l < "$RUN/residue-processes.txt")"
carla_clients "$RUN/carla-clients-after.txt"
echo "ended=$(date -Is)"
