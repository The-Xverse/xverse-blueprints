# Shared preflight and cleanup helpers for run-live.sh and run-baseline.sh (Phase 7 live integration).
L10=/media/jefferson/11c42dee-73a3-4c2b-ab42-a0440011d9e0
CARLA_ENV=$L10/.x-verse-build/cache/xverse-compat-carla-0.9.15-cp310
SITE=$CARLA_ENV/lib/python3.10/site-packages
VENV=$L10/.x-verse-build/cache/xverse-lite-live-20261022/driver-venv

# Revisions with diff hashes; refuses dirty trees unless XVERSE_LIVE_ALLOW_DIRTY=1 (review 1 R-1).
record_revisions() {  # $1 = run dir; remaining = name=path pairs
  local run=$1; shift
  local dirty_total=0
  for pair in "$@"; do
    local name=${pair%%=*} path=${pair#*=}
    local head dirty diffhash
    head=$(git -C "$path" rev-parse HEAD); dirty=$(git -C "$path" status --porcelain | wc -l)
    diffhash=$( (git -C "$path" diff HEAD; git -C "$path" status --porcelain) | sha256sum | cut -c1-64)
    echo "$name $head dirty=$dirty diff-sha256=$diffhash" >> "$run/identities.txt"
    dirty_total=$((dirty_total + dirty))
  done
  if [ "$dirty_total" -gt 0 ] && [ "${XVERSE_LIVE_ALLOW_DIRTY:-0}" != 1 ]; then
    echo "BLOCKED: dirty candidate trees (set XVERSE_LIVE_ALLOW_DIRTY=1 only for development runs)"; return 4
  fi
}

# Identity of a legacy checkout that is recorded but never refused: revision, dirty count and diff hash (S1 FR-016).
legacy_identity() {  # $1 = name, $2 = path
  echo "$1 $(git -C "$2" rev-parse HEAD) dirty=$(git -C "$2" status --porcelain -- . | wc -l) diff-sha256=$( (git -C "$2" diff HEAD -- .; git -C "$2" status --porcelain -- .) | sha256sum | cut -c1-64)"
}

# The xverse-compat checkout must be named explicitly; there is no default candidate path (S1 FR-014).
require_compat() {
  if [ -z "${XVERSE_COMPAT_SRC:-}" ] || [ ! -d "$XVERSE_COMPAT_SRC/src/xverse_compat" ]; then
    echo "BLOCKED: set XVERSE_COMPAT_SRC to an xverse-compat checkout (no default path; S1 FR-014)"; return 4
  fi
}

# Established CARLA connections by process; refuses any client except the session host's localhost port
# detection (moshi-hook), recorded as such (review 1 R-10).
carla_clients() {  # $1 = output file; returns 4 when an unexpected client is connected
  ss -tnp 2>/dev/null | awk '$1 == "ESTAB" && ($4 ~ /:200[01]$/ || $5 ~ /:200[01]$/)' > "$1"
  # any client except moshi-hook blocks, including connections without a users: field (other users' processes, review 2 N-7)
  if grep -v 'moshi-hook' "$1" | grep -qv 'CarlaUE4'; then return 4; fi
}

# World settings as a fresh client sees them (DLG-11).
world_settings() {  # $1 = output JSON, $2 = HOME for the client
  (cd /tmp && env -i PATH=/usr/bin HOME="$2" /usr/bin/python3.10 -s -B -c "
import json, site, sys, time; site.addsitedir('$SITE'); import carla
try:
    c = carla.Client('127.0.0.1', 2000); c.set_timeout(10); w = c.get_world(); s = w.get_settings()
    f0 = w.get_snapshot().frame; time.sleep(1.0); f1 = w.get_snapshot().frame  # DLG-11a: is any client ticking?
except RuntimeError as error:  # a hung or absent server: one line, fail closed (S1 FR-015, T-5 d)
    print('world settings unavailable: %s' % error, file=sys.stderr); sys.exit(1)
print(json.dumps({'synchronousMode': s.synchronous_mode, 'fixedDeltaSeconds': s.fixed_delta_seconds, 'frame': f1,
                  'frameAdvancing': f1 > f0, 'vehicles': [(a.id, a.type_id, a.attributes.get('role_name')) for a in w.get_actors().filter('vehicle.*')]}))") > "$1"
}
