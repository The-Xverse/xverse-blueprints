from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,os,signal,subprocess,time
ROOT=Path(__file__).resolve().parent
CONTROL=Path("/home/jefferson/xverse-platform-worktrees/stabilization-s1a3-20261023/docs/engineering/maestro-lite/evidence/affa19/stabilization-s1a3/platform-regression-20261024j-codex-supervision")
JOBS=json.loads((ROOT/"jobs.json").read_text())
END=datetime(2026,10,24,23,0,tzinfo=ZoneInfo("Europe/Lisbon")).timestamp()
def stamp():return datetime.now(ZoneInfo("UTC")).isoformat()
def state(phase,**kw):
 value=dict(phase=phase,utc=stamp(),**kw);tmp=ROOT/"state.tmp";tmp.write_text(json.dumps(value,indent=2)+"\n");os.replace(tmp,ROOT/"state.json");print(value,flush=True)
def pytest_busy():
 for p in Path("/proc").iterdir():
  if not p.name.isdigit():continue
  try:a=(p/"cmdline").read_bytes().split(b"\0")
  except OSError:continue
  if b"pytest" in a or any(Path(x.decode(errors="replace")).name=="run_blueprints_pytest.py" for x in a if x) or (a and Path(a[0].decode(errors="replace")).name=="pytest"):return True
 return False
try:
 predecessor=ROOT.with_name("codex-post-platform-repair-verification-20261024")/"state.json"
 state("waiting-for-predecessor-queue")
 while not predecessor.is_file() or json.loads(predecessor.read_text())["phase"]!="terminal":
  if time.time()>=END:state("not-started-soak-cutoff");raise SystemExit(3)
  time.sleep(5)
 state("waiting-for-platform",jobs=len(JOBS))
 while True:
  status=json.loads((CONTROL/"state.json").read_text());out=Path(status["output"])
  if (out/"wheel-receipt.json").is_file() and not pytest_busy():break
  if time.time()>=END:state("not-started-soak-cutoff");raise SystemExit(3)
  time.sleep(15)
 state("platform-released",platform_status=status["phase"],platform_receipt=str(out/"wheel-receipt.json"))
 results=[]
 for job in JOBS:
  while pytest_busy() and time.time()<END-job["timeout_s"]-60:time.sleep(15)
  if time.time()>=END-job["timeout_s"]-60:
   results.append(dict(id=job["id"],state="not-started-soak-cutoff"));continue
  head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=job["repository"],text=True).strip()
  dirty=subprocess.check_output(["git","status","--porcelain","--untracked-files=no"],cwd=job["repository"],text=True).strip()
  if head!=job["revision"] or dirty:
   results.append(dict(id=job["id"],state="not-started-input-drift",head=head,tracked_dirty=bool(dirty)));continue
  directory=ROOT/job["id"];directory.mkdir(exist_ok=False)
  env=dict(os.environ);env.pop("PYTHONPATH",None);env.pop("PYTEST_ADDOPTS",None);env.update(job["environment"])
  began=time.monotonic();timeout=False
  with (directory/"pytest.log").open("x") as log:
   process=subprocess.Popen(job["command"],cwd=job["cwd"],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   state("running",job=job["id"],pid=process.pid,revision=head)
   try:rc=process.wait(timeout=job["timeout_s"])
   except subprocess.TimeoutExpired:
    timeout=True;os.killpg(process.pid,signal.SIGTERM)
    try:rc=process.wait(timeout=15)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);rc=process.wait()
  data=(directory/"pytest.log").read_bytes();lines=data.decode(errors="replace").splitlines()
  receipt=dict(job,returncode=rc,timed_out=timeout,finished_utc=stamp(),elapsed_s=round(time.monotonic()-began,3),log_sha256=hashlib.sha256(data).hexdigest(),tail=lines[-12:],accepted=False,merged=False)
  (directory/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
  results.append(dict(id=job["id"],state="passed" if rc==0 else "failed",receipt=str(directory/"receipt.json")))
  state("job-terminal",job=job["id"],returncode=rc)
 (ROOT/"results.json").write_text(json.dumps(results,indent=2)+"\n");state("terminal",results=results)
except Exception as exc:state("queue-error",error=repr(exc));raise
