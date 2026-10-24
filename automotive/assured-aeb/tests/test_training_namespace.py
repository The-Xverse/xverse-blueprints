"""Tiny genuine -rn/FD and stdlib refusal controls; all bounds/records are TEST-ONLY, no fitting/frameworks."""
import copy
import errno
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from assured_aeb.perception import training_worker as W
from assured_aeb.perception.training_io import canonical
import training4b_supervisor as S


CHILD = r'''
import errno,json,os,sys
from pathlib import Path
from assured_aeb.perception import training_worker as W
from assured_aeb.perception.training_io import canonical
record=json.loads(sys.argv[1]);mode=sys.argv[2]
readlink=os.readlink
def self_only(path):
    assert str(path).startswith('/proc/self/'), 'parent proc dereference forbidden'
    return readlink(path)
os.readlink=self_only
proof=W.ParentNamespaceProof.adopt(canonical(record),max_record_bytes=1000000)
out=dict(schema='TEST-ONLY-namespace-proof-control/1',mode=mode)
try:
    with proof:
        if mode=='preload':sys.modules['torch']=object()
        if mode=='same-user-emulated':
            original=W._self_namespace_snapshot
            def snapshot():
                own=list(original());p=record['user']
                own[1]=(W.NAMESPACE_TYPES['user'],p['device'],p['inode'])
                return tuple(own)
            W._self_namespace_snapshot=snapshot
        if mode in ('bad-job','bad-stage'):
            def forbidden(*args,**kwargs):raise AssertionError('bad input reached isolation/effects')
            W.check_worker_isolation=forbidden
            job=b'{}' if mode=='bad-job' else Path(sys.argv[3]).read_bytes()
            W.run_training(job,b'{}',b'{}',max_record_bytes=1000000,identity_path='/TEST-ONLY/identity',
                lock_path='/TEST-ONLY/lock',parent_namespace_proof=proof,
                output_directory=Path(os.environ['TMPDIR'])/'never-created')
        else:
            own=W.check_worker_isolation(proof)
            assert W._self_namespace_snapshot()==own
            out['ownIdentities']=own
        out['state']='validated'
except (ValueError,OSError) as error:
    out.update(state='refused',error=str(error),errorClass=type(error).__name__)
finally:
    proof.close()
    if mode=='preload':sys.modules.pop('torch',None)
for name in ('net','user'):
    try:os.fstat(record[name]['fd'])
    except OSError as error:assert error.errno==errno.EBADF
    else:raise AssertionError('inherited proof handle leaked')
assert not (Path(os.environ['TMPDIR'])/'never-created').exists()
assert not any(name.split('.')[0] in ('torch','numpy','onnxruntime') for name in sys.modules)
out['proofClosed']=True;out['frameworksImported']=False
print(json.dumps(out,sort_keys=True))
'''


class TrainingNamespaceTests(unittest.TestCase):
    def setUp(self):
        retained = os.environ.get("XVERSE_NAMESPACE_CONTROL_ROOT")
        if retained:
            self.root = Path(retained) / self._testMethodName
            self.root.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory(prefix="training-namespace-")
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        for name in ("cache", "cache/torch", "cache/inductor", "cache/triton"):
            (self.root / name).mkdir()
        self.count = 0

    def closed(self, fd):
        with self.assertRaises(OSError) as caught:
            os.fstat(fd)
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def child(self, mode="success", *, user_only=False):
        source = Path(__file__).resolve().parents[1]
        paths = [str(source), str(source / "tests")]
        compat = os.environ.get("XVERSE_COMPAT_SRC")
        if compat:
            paths.append(compat)
        environment = dict(PATH="/usr/bin:/bin", HOME="/nonexistent-namespace-control", PYTHONDONTWRITEBYTECODE="1",
            PYTHONPATH=os.pathsep.join(paths), TMPDIR=str(self.root), XDG_CACHE_HOME=str(self.root / "cache"),
            TORCH_HOME=str(self.root / "cache/torch"), TORCHINDUCTOR_CACHE_DIR=str(self.root / "cache/inductor"),
            TRITON_CACHE_DIR=str(self.root / "cache/triton"))
        if mode == "bad-cache":
            environment["XDG_CACHE_HOME"] = str(self.root.parent)
        directory = self.root / str(self.count);directory.mkdir();self.count += 1
        with W.captured_parent_namespaces() as (original, descriptors, observe):
            record = copy.deepcopy(original)
            if mode == "parent":record["parentPid"] += 1
            flags = ["-S", "-B"] if mode == "flags" else ["-S", "-s", "-B"]
            command = ["unshare", "-r" if user_only else "-rn", sys.executable, *flags, "-c", CHILD,
                       canonical(record).decode(), mode, str(self.root / "job.json")]
            result = S.capture_attempt(command, environment=environment, cwd=source, directory=directory,
                timeout_seconds=10, term_seconds=1, kill_seconds=2, pass_fds=descriptors,
                identity_reader=observe, context={"purpose":"TEST-ONLY namespace source control", "mode":mode})
            self.assertEqual(observe(), original)
            self.assertEqual(result["passed_fds"], list(descriptors))
            self.assertTrue(all(not os.get_inheritable(fd) for fd in descriptors))
        for fd in descriptors:self.closed(fd)
        self.assertTrue(result["capture_complete"], result)
        self.assertEqual(result["returncode"], 0, (directory / "worker.stderr").read_text())
        out = json.loads((directory / "worker.stdout").read_text())
        self.assertTrue(out["proofClosed"]);self.assertFalse(out["frameworksImported"])
        return out

    def test_genuine_rn_types_identities_and_close_without_parent_proc_or_frameworks(self):
        self.assertEqual(self.child()["state"], "validated")

    def test_genuine_child_refusal_closes_proof_on_flags_preload_parent_and_cache_failure(self):
        for mode, expected in (("flags", "-S -s -B"), ("preload", "framework already imported"),
                               ("parent", "parent changed"), ("bad-cache", "explicit cache")):
            with self.subTest(mode=mode):
                out = self.child(mode);self.assertEqual(out["state"], "refused");self.assertIn(expected, out["error"])

    def test_nonfresh_network_and_emulated_same_user_are_refused(self):
        # -r-only is a deliberate NEGATIVE control, never a fallback/success path.
        self.assertEqual(self.child(user_only=True)["state"], "refused")
        self.assertEqual(self.child("same-user-emulated")["state"], "refused")

    def test_bad_job_and_stage_refuse_before_isolation_effects_but_cli_lease_closes(self):
        from training4a_fixture import build
        fixture = build(self.root / "fixture")
        (self.root / "job.json").write_bytes(canonical(fixture[0]))
        for mode in ("bad-job", "bad-stage"):
            with self.subTest(mode=mode):self.assertEqual(self.child(mode)["state"], "refused")

    def duplicates(self, original):
        record = copy.deepcopy(original)
        descriptors = []
        for name in ("net", "user"):
            fd = os.dup(original[name]["fd"]);descriptors.append(fd);record[name]["fd"] = fd
        return record, descriptors

    def cleanup_descriptors(self, descriptors):
        for fd in descriptors:
            try:os.close(fd)
            except OSError as error:self.assertEqual(error.errno, errno.EBADF)

    def test_wrong_identity_or_type_closes_all_typed_adopted_handles(self):
        with W.captured_parent_namespaces() as (original, _, _):
            for mutation in ("device", "inode", "swap"):
                record, descriptors = self.duplicates(original)
                try:
                    if mutation == "swap":record["net"]["fd"],record["user"]["fd"] = record["user"]["fd"],record["net"]["fd"]
                    else:
                        record["net"][mutation] += 1
                        record["net"]["reference"] = f"net:[{record['net']['inode']}]"
                    with self.assertRaises(ValueError):W.ParentNamespaceProof.adopt(canonical(record), max_record_bytes=1000000)
                    for fd in descriptors:self.closed(fd)
                finally:self.cleanup_descriptors(descriptors)

    def test_nonproof_file_pipe_socket_and_recycled_number_are_never_closed(self):
        with W.captured_parent_namespaces() as (original, _, _):
            with tempfile.TemporaryFile(dir=self.root) as file, socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                read, write = os.pipe()
                try:
                    for sentinel in (file.fileno(), sock.fileno(), read):
                        record, descriptors = self.duplicates(original)
                        os.close(descriptors[0]);descriptors = descriptors[1:]
                        record["net"]["fd"] = sentinel
                        try:
                            with self.assertRaises(ValueError):W.ParentNamespaceProof.adopt(canonical(record), max_record_bytes=1000000)
                            os.fstat(sentinel)
                            for fd in descriptors:self.closed(fd)
                        finally:self.cleanup_descriptors(descriptors)
                finally:os.close(read);os.close(write)
            record, descriptors = self.duplicates(original)
            old = descriptors[0];os.close(old)
            with (self.root / "sentinel").open("wb") as sentinel:
                self.assertEqual(sentinel.fileno(), old)  # Deliberately exercise number reuse on this owned stream.
                record["net"]["fd"] = old
                try:
                    with self.assertRaises(ValueError):W.ParentNamespaceProof.adopt(canonical(record), max_record_bytes=1000000)
                    os.fstat(sentinel.fileno());self.closed(descriptors[1])
                finally:self.cleanup_descriptors(descriptors[1:])

    def test_malformed_proof_never_adopts_std_or_unrelated_descriptors_and_close_is_idempotent(self):
        with W.captured_parent_namespaces() as (original, _, _):
            for bad in (None, True, -1, 0, 1, 2, "3"):
                record = copy.deepcopy(original);record["net"]["fd"] = bad
                with self.assertRaises(ValueError):W.ParentNamespaceProof.adopt(canonical(record), max_record_bytes=1000000)
                for name in ("net", "user"):os.fstat(original[name]["fd"])
            for mutate in (lambda r:r.update(extra=True), lambda r:r["net"].update(reference="invented"),
                           lambda r:r["user"].update(fd=r["net"]["fd"])):
                record = copy.deepcopy(original);mutate(record)
                with self.assertRaises(ValueError):W.ParentNamespaceProof.adopt(canonical(record), max_record_bytes=1000000)
                for name in ("net", "user"):os.fstat(original[name]["fd"])
            record, descriptors = self.duplicates(original)
            proof = W.ParentNamespaceProof.adopt(canonical(record), max_record_bytes=1000000)
            proof.close()
            with (self.root / "after-close").open("wb") as sentinel:
                proof.close();os.fstat(sentinel.fileno())
            for fd in descriptors:self.closed(fd)

    def test_parent_second_acquisition_failure_closes_first_and_supervisor_rejects_bad_pass_fds(self):
        original = open;handles = []
        def acquire(path, *args, **kwargs):
            if path == "/proc/self/ns/user":raise OSError("TEST-ONLY second acquisition failure")
            handle = original(path, *args, **kwargs);handles.append(handle);return handle
        with patch.object(W, "open", acquire, create=True):
            with self.assertRaises(OSError):
                with W.captured_parent_namespaces():self.fail("yielded partial proof")
        self.assertTrue(handles[0].closed)
        for bad in ((0,), (True,), (-1,), (3,3), [3]):
            with self.assertRaises(ValueError):
                S.capture_attempt([],environment={},cwd=self.root,directory=self.root,timeout_seconds=1,
                    term_seconds=1,kill_seconds=1,identity_reader=lambda:{},context={},pass_fds=bad)

    def test_owned_pass_fds_survive_spawn_interrupt_cleanup_then_parent_finally_closes(self):
        # Generic supervisor ownership control; no training/plain-process fallback or framework work.
        original_popen = subprocess.Popen
        for after_assignment in (False, True):
            directory = self.root / str(after_assignment);directory.mkdir()
            owned = []
            with W.captured_parent_namespaces() as (record, descriptors, observe):
                def spawn(*args, **kwargs):
                    self.assertTrue(kwargs["close_fds"]);self.assertEqual(kwargs["pass_fds"], descriptors)
                    process = original_popen(*args, **kwargs);owned.append(process)
                    if not after_assignment:
                        signal.raise_signal(signal.SIGINT)
                    else:
                        wait = process.wait
                        first = True
                        def interrupted(*args, **kwargs):
                            nonlocal first
                            if first:
                                first = False;signal.raise_signal(signal.SIGTERM)
                            return wait(*args, **kwargs)
                        process.wait = interrupted
                    return process
                try:
                    with patch.object(S.subprocess, "Popen", spawn):
                        result = S.capture_attempt([sys.executable,"-I","-B","-c","import time;time.sleep(30)"],
                            environment=dict(os.environ),cwd=self.root,directory=directory,timeout_seconds=3,
                            term_seconds=0.2,kill_seconds=2,identity_reader=observe,context={},pass_fds=descriptors)
                    self.assertFalse(result["capture_complete"]);self.assertIn("AttemptInterrupted",result["failure"])
                    self.assertTrue(result["cleanup"]["complete"]);self.assertFalse(S._group_exists(owned[0].pid))
                    self.assertEqual(observe(), record)
                finally:
                    for process in owned:S._cleanup(process,0.2,2)
            for fd in descriptors:self.closed(fd)

    def test_emulated_isolation_and_unsupported_ioctl_refusals_close_only_adopted_proof(self):
        with W.captured_parent_namespaces() as (original, _, _):
            record, descriptors = self.duplicates(original)
            try:
                with patch.object(W.fcntl,"ioctl",side_effect=OSError(errno.ENOTTY,"TEST-ONLY unsupported ioctl")):
                    with self.assertRaises(ValueError):W.ParentNamespaceProof.adopt(canonical(record),max_record_bytes=1000000)
                # Unvalidated resources were never adopted; ownership stays with this caller.
                for fd in descriptors:os.fstat(fd)
            finally:self.cleanup_descriptors(descriptors)
            for failure in (OSError("TEST-ONLY own namespace unavailable"), ValueError("TEST-ONLY self observation refusal")):
                record, descriptors = self.duplicates(original)
                record["parentPid"] = os.getppid()  # Emulated parent binding for this refusal-only control.
                proof = W.ParentNamespaceProof.adopt(canonical(record),max_record_bytes=1000000)
                fake_sys=SimpleNamespace(platform=sys.platform,flags=SimpleNamespace(no_site=1,no_user_site=1,dont_write_bytecode=1),modules={})
                with patch.object(W,"sys",fake_sys),patch.object(W,"_self_namespace_snapshot",side_effect=failure):
                    with self.assertRaises(type(failure)):W.check_worker_isolation(proof)
                for fd in descriptors:self.closed(fd)
            with patch.object(W.os,"getuid",return_value=1):
                with self.assertRaisesRegex(ValueError,"unshare -r"):
                    W._self_namespace_snapshot()
            with patch.object(W.os,"getuid",return_value=0),patch.object(W.Path,"read_text",return_value="header\nheader\nlo: 0\nextra0: 0\n"):
                with self.assertRaisesRegex(ValueError,"not isolated to loopback"):
                    W._self_namespace_snapshot()


if __name__ == "__main__":
    unittest.main()
