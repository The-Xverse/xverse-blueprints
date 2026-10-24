# Training4b inherited parent namespace proof — detailed design before repair

2026-10-24. **DESIGN PROPOSAL for root/independent review; no product or driver repair yet.**
Source pin20af4185371735ebd240830ec869e74bb0dc8f51. Root accepts the two-descriptor direction below, preserving
the actual fresh `unshare -rn` requirement. Exact implementation still needs independent detailed review.
Sol/high is recommended for descriptor ownership, namespace semantics and cancellation review. No model switch
or measured cost claim. This is offline engineering isolation, not C1/live execution or hostile-worker containment.

## 1. Actual failure and unchanged boundaries

The full owning suite passed1104/5subtests, but the first genuine isolated case failed before framework import:
training_worker.check_worker_isolation readlink of /proc/<parent>/ns/net raises PermissionError in the child user
namespace. Source order then has the same inaccessible parent user-namespace read. A successful mocked/offline
suite did not exercise this cross-userns access policy. Exact original worker/outer receipts and stdout/stderr
are preserved under docs/evidence/training4b-parent-ns-failure-20261024, with source paths/hashes in
design-input-bindings.json. They remain a failed attempt; complete capture/cleanup is not successful training.

Change only the named4b worker and owned test-driver/supervisor/tests/contracts as later authorized. Keep4a's
training_record.py, training_io.py, dataset_consumer.py byte-identical and preserve its three-file closure. The
four-file4b closure includes training_worker.py and **must change explicitly** if its namespace contract changes;
fresh stage records/reports bind that new actual closure. No silent repinning of old stages/jobs/failed artifacts.
Fit methods, network, weights/loss/checkpoint/data-split rules and preprocessing are outside this repair.

No plain-process, unshare -cn, missing-namespace, invented parent-string or optional-success proof fallback.
The genuine driver continues exact unshare -rn, admitted actual Python, -S -s -B, explicit sites/scratch/cache,
CPU-only/preload/path/environment checks and existing worker/group timeouts. FD/PID/namespace observations stay
outside deterministic learned weights/descriptors/report; existing operational receipts retain them separately.

## 2. Primary API basis and support scope

Read actual local /usr/include/linux/nsfs.h and the matching Linux6.8.0-138 header, linux/sched.h, the x86_64
asm/ioctl.h include and asm-generic/ioctl.h. Exact bytes/paths are bound in design-input-bindings.json.
NS_GET_NSTYPE is _IO(0xb7,3); the reviewed x86_64 generic encoding yields **0xb703**. Namespace type values are
CLONE_NEWNET=0x40000000 and CLONE_NEWUSER=0x10000000. These are kernel UAPI constants, not scientific parameters
or guessed namespace IDs. Guard the reviewed Linux/x86_64 ABI explicitly; unsupported ioctl/ABI refuses before
frameworks rather than inventing a different constant or assuming an arbitrary fd is a namespace.

The pinned Linux6.8 nsfs implementation returns the namespace operation type for NS_GET_NSTYPE; its namespace
identity helper uses the namespace device/inode pair. This supports typed fstat identity comparison without a
parent procfs lookup or an owning-userns inference. [Linux6.8 nsfs implementation](https://raw.githubusercontent.com/torvalds/linux/v6.8/fs/nsfs.c).
This source reasoning is not an executed genuine child proof. Do not use NS_GET_USERNS as a shortcut: the owner of
the parent's network namespace need not be the parent's current user namespace, and related-namespace traversal
introduces additional permissions. No ctypes/statfs ABI, setns, signaling or network action is needed here.

## 3. Exact operational proof contract

Replace --parent-netns text with mandatory --parent-namespace-proof containing bounded canonical JSON. It is an
operational launcher observation, not a job/method parameter or model metadata record. Its exact closed shape is:

```text
{
  schema: "assured-aeb.parent-namespace-proof/1",
  parentPid: <actual original launcher PID>,
  net:  {fd: <owned inherited fd>, device: <fstat st_dev>, inode: <fstat st_ino>, reference: <actual own readlink>},
  user: {fd: <owned inherited fd>, device: <fstat st_dev>, inode: <fstat st_ino>, reference: <actual own readlink>}
}
```

Integers are exact native ints, never bool/coerced text. parentPid positive; fds distinct and >=3; device/inode
actual nonnegative/positive kernel results. reference is exactly the captured net:[inode] or user:[inode] form,
and agrees with the sampled descriptor inode; no fallback to reference-string inequality. Canonical bytes are
bounded by the existing explicit max-record-bytes argument, with no new guessed input limit. Extra/missing keys,
invalid numeric fields, duplicated fds and wrong namespace types refuse. This exact launcher is trusted to capture
its own references; the ABI is not proof against a malicious launcher passing fabricated observations.

The worker adopts the explicit inherited descriptor pair as an owning ParentNamespaceProof/lease, with exactly
these observations and close ownership, never arbitrary fd ranges. Genuine run_training receives this mandatory
typed live proof through a keyword such as parent_namespace_proof; the old string argument is removed/refused.
No caller-supplied optional success predicate, guessed namespace text, global cached proof or ordinary-process
success path is introduced. Capture API updates must not make proof optional in the genuine training driver.

## 4. Parent capture, ownership and spawn interruption

1. The original driver opens its **own** /proc/self/ns/net and /proc/self/ns/user before Popen/unshare. These kernel
   magic links must intentionally be followed; O_NOFOLLOW is not appropriate for opening the actual namespace
   object. Use read-only CLOEXEC owned file objects/contexts, with immediate close ownership so failure acquiring
   the second cannot leak the first. Default parent descriptors stay non-inheritable; verify that property.
2. Validate each fd by NS_GET_NSTYPE, read-only flags, fstat and genuine self readlink. Capture parentPid/dev/inode/
   references directly while holding both open. Re-observe original parent current identity before spawn/after
   cleanup through those retained own handles/self paths, not a made-up or stale caller number. Keep contexts
   around the whole capture_attempt including its before/after identity reader and receipt finalization.
3. Extend the generic supervisor with explicit validated pass_fds (empty may remain allowed only for its existing
   unrelated synthetic supervisor controls). The genuine driver always supplies exactly (netfd,userfd), and
   subprocess.Popen uses **close_fds=True, pass_fds=(netfd,userfd)**, start_new_session=True and the original owned
   capture paths/environment. No global inheritable toggling, preexec_fn, socket inheritance or arbitrary extra fd.
4. Preserve the existing deferred-signal spawn ownership: capture process handle before acting on a pending signal,
   then bounded cleanup/reap/group absence before releasing parent proof fds. New fd plumbing cannot bypass the
   pre-reserved receipt, interruption shielding, original handlers/mask restoration or TERM/KILL deadlines.
5. Parent finally closes its own two handles exactly once on normal/nonzero/timeout/cancellation, Popen failure,
   interruption before/after assignment, identity-reader or receipt/write failure. Context-managed file-object
   acquisition avoids a raw-integer open/assignment leak window. Failure before a child exists closes acquired
   handles and preserves partial diagnostics; failure after spawn retains original supervisor group ownership.

The parent does not close a child fd by number, and closing its own handle does not change the child's copied
kernel reference. Child proof lifetime below ends before framework imports. Fatal supervisor SIGKILL is not a
Python cleanup guarantee; keep the existing trusted-group/worker-timeout limitation explicit rather than claim a
new orphan-containment mechanism. No parent PID/FD observation belongs in the learned deterministic report.

## 5. Child admission, refusal cleanup and own-namespace stability

The CLI boundary adopts the declared pair before entering the API and owns its idempotent close in a finally/
context. Validate numeric fd arguments before adoption; never close stdin/stdout/stderr, close an arbitrary range,
or open self descriptors after an invalid closed proof number then accidentally close its recycled number.
Track only the two explicitly adopted child-copy handles and the actual self handles opened by this check.

For each inherited handle, immediately mark the child copy non-inheritable/CLOEXEC, validate it exists/read-only,
is the typed expected namespace through NS_GET_NSTYPE and its fstat(dev,ino) matches the actual supplied parent
observations. A regular file/pipe/socket, wrong namespace type, changed identity, unavailable/closed fd or syscall
failure refuses. Wrapping the explicitly adopted fd in an owning file object/context ensures wrong-type/refusal
paths close that child copy once; malformed unadopted/std fd arguments are not blindly closed. Child process exit
also closes inherited handles after argparse/early fatal refusal, without a framework/output side effect.

Open the child's **own** /proc/self/ns/net and /proc/self/ns/user read-only/CLOEXEC, query their types and fstat
identities. Require inherited parent-net != actual self-net AND inherited parent-user != actual self-user.
Require actual os.getuid()==0 and actual current self net/dev has only loopback, preserving the existing -r/-n
checks. Require actual getppid()==the original recorded parentPid for this exact no---fork unshare/exec driver;
reparenting or a different wrapping process refuses. Do not read /proc/<parent>/ns/* or infer userns identity
from the network namespace's owner. Namespace strings alone cannot establish any of these predicates.

Return only an immutable internal own-net/own-user identity observation for later stability checks. Close all
inherited proof and temporary self descriptors **before** environment-tree verification/framework imports, whether
validation succeeds or refuses. The outer CLI context is idempotent on already-closed proof. Hold no parent
namespace handle during Torch work or in framework descendant/thread state. No setns/unshare retry/fallback.
After fitting, reopen/query own self namespace handles and compare both original own identities, plus UID0/loopback
and no-ORT as applicable, before output. Identity checks use kernel objects, not a stale readlink-only string.

## 6. Bad job-before-effects API and closure impact

Keep run_training job→stage→locations admission before check_worker_isolation, dataset/environment work, output
creation, limits/thread/framework/model effects. Bad-job/stage tests pass the required new proof keyword with an
invalid sentinel that can never satisfy genuine successful admission; their isolation function must still never
be called, and output/framework sets remain unchanged. This is an invalid-input control, not an optional proof
for a real worker. Successful API calls require a typed adopted live proof. CLI descriptor-adoption/close ownership
is transport housekeeping before/around that API, explicitly separate from its scientific/job effect boundary.

If bounded file read/job/stage/locations admission fails, CLI finally closes adopted inherited copies. If isolation
fails, it closes proof/self handles and never verifies the environment tree/imports frameworks/writes output.
Do not move job validation after a framework import just to simplify proof handling. Avoid closing caller-owned
random fds on an invalid direct API sentinel; only the adopted proof lease owns closes.

training_worker.py is one of the named four4b source files, so code_digest/stage closure/report source identity
changes explicitly. Add no new product file outside that closure without a separate disposition. Driver/supervisor
hashes/actual command/proof/cleanup appear only in fresh operational receipts. All three4a sources and their closure
remain byte-identical to20af418. Learned report format receives no new namespace/PID/fd/host-timing fields; repeats
with different fd/PID/ns identities must still match deterministic bytes under the same new stage/source closure.

## 7. Meaningful verification obligations before genuine fitting closure

- Tiny genuine unshare -rn stdlib control: original parent pre-opens net/user pair, passes only them, child
  NS_GET_NSTYPE/fstat both match parent observations, both differ from own, UID0/loopback; close all handles and
  prove no framework import. Record actual command, code/header hashes/status and bounded cleanup on loop10.
  This must use the real path, not monkeypatched identity equality. Unsupported facilities are failed/unavailable
  verification, never a plain-process pass.
- Exact refusals: invented reference with a real fd; wrong dev/ino; swapped net/user; same-namespace fd; duplicated,
  missing, closed, negative/bool/std fd; ordinary regular-file/pipe/socket fd; unsupported ioctl; wrong parent PID;
  same network or same user namespace; non-root UID; extra interface; unavailable self observation; preloaded
  framework or bad -S/-s/-B. Distinguish real small fd controls from emulated syscall error controls.
- Ownership: parent failure before/after second acquisition; child failure at each adoption/type/reference/self
  check; no descriptor-number reuse/double-close; parent descriptors remain live/non-inheritable during capture
  and close after every return/exception. No arbitrary/std fd is closed. A non-proof sentinel resource stays open.
- Re-run affected existing real supervisor controls: interruption during spawn before assignment and after
  assignment, timeout/descendant TERM-ignore/KILL/reap, missing executable, capture I/O/identity failure and masks/
  handlers restored. Assert exactly the two intended fds in Popen and no inherited blocked signals. Fresh cleanup
  deadlines remain unchanged; no pytest/framework needed to review these source-level mechanics.
- Exact bad-job/stage-before-isolation/output/framework tests under new required signature; source closure changes
  invalidate old stage records;4a's three-file identity remains stable. No environment tree walk is needed for
  these guards. Proof handles closed before the first verify_environment/framework seam on success/refusal.
- Root-scheduled owning suite then genuine repeated training: both identical cases' deterministic files/report
  equal under the new closure despite distinct operational process/fd/ns identities; held-out mutation leaves
  selected fit weights unchanged; actual nonfinite fitting refusal remains the decisive original classifier.
  Preserve all original failed artifacts, no overwrite/relabel and no claim4c–4e/model-quality/live approval.

This design pass executed no namespace worker, pytest/framework, Torch/NumPy/ORT, environment-tree scan, C1/kernel
probe, simulator/factory/live run or repair. Actual work so far is source/header/kernel-source reading plus tiny
receipt/header hash checks and exact retention of original failure records. Root must independently disposition
this detailed contract before any worker/driver product repair; later execution uses its serialized slot.
