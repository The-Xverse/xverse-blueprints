"""Real tiny subprocess controls; every duration/value is TEST-ONLY, never framework training."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import training4b_supervisor as S


class TrainingSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='training-supervisor-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def capture(self, script='print("real child", flush=True)', **changes):
        settings = dict(command=[sys.executable, '-I', '-B', '-c', script], environment=dict(os.environ),
                        cwd=self.root, directory=self.root, timeout_seconds=3, term_seconds=0.2,
                        kill_seconds=3, identity_reader=lambda: {'TEST-ONLY-input': 'unchanged'},
                        context={'purpose': 'TEST-ONLY-supervisor-control'})
        settings.update(changes)
        return S.capture_attempt(**settings)

    def test_normal_and_actual_nonzero_are_distinct_complete_captures(self):
        result = self.capture('import signal;print("actual stdout",flush=True);print("actual stderr",file=__import__("sys").stderr,flush=True);assert not signal.pthread_sigmask(signal.SIG_BLOCK,set())')
        self.assertTrue(result['capture_complete'])
        self.assertEqual(result['returncode'], 0)
        self.assertEqual((self.root/'worker.stdout').read_text(), 'actual stdout\n')
        self.assertEqual((self.root/'worker.stderr').read_text(), 'actual stderr\n')
        self.assertEqual(json.loads((self.root/'worker-execution.json').read_bytes()), result)
        other = self.root/'nonzero'; other.mkdir()
        result = self.capture('raise SystemExit(7)', directory=other)
        self.assertTrue(result['capture_complete'])
        self.assertEqual(result['returncode'], 7)

    def test_timeout_retains_partial_diagnostics_and_refuses_success(self):
        result = self.capture('import time,sys;print("partial-out",flush=True);print("partial-err",file=sys.stderr,flush=True);time.sleep(30)', timeout_seconds=1)
        self.assertFalse(result['capture_complete'])
        self.assertTrue(result['timed_out'])
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual((self.root/'worker.stdout').read_text(), 'partial-out\n')
        self.assertEqual((self.root/'worker.stderr').read_text(), 'partial-err\n')

    def test_spawn_assignment_interrupt_retains_actual_handle_and_cleans_group(self):
        original = subprocess.Popen
        owned = []
        def spawn(*args, **kwargs):
            process = original(*args, **kwargs)
            owned.append(process)
            signal.raise_signal(signal.SIGINT)  # Actual child exists, supervisor has not received its handle yet.
            return process
        try:
            with patch.object(S.subprocess, 'Popen', spawn):
                result = self.capture('import time;time.sleep(30)')
            self.assertFalse(result['capture_complete'])
            self.assertIn('AttemptInterrupted', result['failure'])
            self.assertTrue(result['cleanup']['complete'])
            self.assertEqual(len(owned), 1)
            self.assertFalse(S._group_exists(owned[0].pid))
        finally:
            for process in owned:
                S._cleanup(process, 0.2, 3)

    def test_post_assignment_interruption_always_cleans_owned_group(self):
        original = subprocess.Popen
        owned = []
        def spawn(*args, **kwargs):
            process = original(*args, **kwargs)
            owned.append(process)
            wait = process.wait
            first = True
            def interrupted_wait(*args, **kwargs):
                nonlocal first
                if first:
                    first = False
                    signal.raise_signal(signal.SIGTERM)
                return wait(*args, **kwargs)
            process.wait = interrupted_wait
            return process
        try:
            with patch.object(S.subprocess, 'Popen', spawn):
                result = self.capture('import time;time.sleep(30)')
            self.assertFalse(result['capture_complete'])
            self.assertTrue(result['cleanup']['complete'])
            self.assertIn('AttemptInterrupted', result['failure'])
            self.assertFalse(S._group_exists(owned[0].pid))
        finally:
            for process in owned:
                S._cleanup(process, 0.2, 3)

    def test_missing_executable_and_input_drift_are_failed_captures(self):
        result = self.capture(command=[str(self.root/'absent-executable')])
        self.assertFalse(result['capture_complete'])
        self.assertIsNone(result['returncode'])
        self.assertIn('FileNotFoundError', result['failure'])
        self.assertTrue(result['cleanup']['complete'])
        other = self.root/'drift'; other.mkdir()
        calls = iter([{'input': 1}, {'input': 2}])
        result = self.capture(directory=other, identity_reader=lambda: next(calls))
        self.assertFalse(result['capture_complete'])
        self.assertEqual(result['returncode'], 0)

    def test_existing_receipt_or_diagnostics_are_preserved_without_spawn(self):
        path = self.root/'worker.stdout'; path.write_bytes(b'original')
        with patch.object(S.subprocess, 'Popen', side_effect=AssertionError('spawn forbidden')):
            with self.assertRaises(FileExistsError):
                self.capture()
        self.assertEqual(path.read_bytes(), b'original')

    def test_nonfinite_keyword_crash_or_unrelated_exception_cannot_count_as_refusal(self):
        scripts = (
            ('import os,signal,sys;print("ValueError: nonfinite loss",file=sys.stderr,flush=True);os.kill(os.getpid(),signal.SIGKILL)', False),
            ('import sys;print("warning: overflow",file=sys.stderr,flush=True);raise ImportError("unrelated")', False),
            ('raise ValueError("nonfinite per-example loss")', True),
            ('raise RuntimeError("value cannot be converted without overflow")', True),
            ('raise OverflowError("unrelated numeric problem")', False),
        )
        for index, (script, expected) in enumerate(scripts):
            with self.subTest(index=index):
                directory = self.root/str(index); directory.mkdir()
                result = self.capture(script, directory=directory)
                self.assertTrue(result['capture_complete'])
                tail = (directory/'worker.stderr').read_text()
                self.assertEqual(S.expected_nonfinite_refusal(result, tail, directory/'absent-output'), expected)
                if expected:
                    (directory/'absent-output').symlink_to(directory/'missing-target')
                    self.assertFalse(S.expected_nonfinite_refusal(result, tail, directory/'absent-output'))

    def test_term_ignoring_descendant_requires_kill_and_actual_group_disappearance(self):
        # Harness-only Linux subreaper prevents orphaned zombies; restore prior setting after owned reaping.
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        stop = threading.Event()
        child = []
        reaped = []
        def reap():
            while not stop.is_set():
                if not child:
                    try:
                        lines = (self.root/'worker.stdout').read_text().splitlines()
                        if lines:
                            child.append(int(lines[0]))
                    except (OSError, ValueError):
                        pass
                if child:
                    try:
                        pid, status = os.waitpid(child[0], os.WNOHANG)
                        if pid:
                            reaped.append((pid, status)); return
                    except ChildProcessError:
                        pass
                stop.wait(0.01)
        thread = threading.Thread(target=reap, daemon=True)
        thread.start()
        script = '''import signal,subprocess,sys,time
signal.signal(signal.SIGTERM,signal.SIG_IGN)
child=subprocess.Popen([sys.executable,'-I','-B','-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(30)'],stdout=subprocess.PIPE,text=True)
assert child.stdout.readline().strip()=='ready'
print(child.pid,flush=True)
time.sleep(30)
'''
        try:
            result = self.capture(script, timeout_seconds=3)
            thread.join(timeout=3)
            self.assertTrue(result['timed_out'])
            self.assertFalse(result['capture_complete'])
            self.assertTrue(result['cleanup']['term_sent'])
            self.assertTrue(result['cleanup']['kill_sent'])
            self.assertTrue(result['cleanup']['complete'], result)
            self.assertTrue(reaped)
        finally:
            stop.set(); thread.join(timeout=3)
            if child and not reaped:
                try:
                    os.kill(child[0], signal.SIGKILL)
                    os.waitpid(child[0], 0)
                except ProcessLookupError:
                    pass
                except ChildProcessError:
                    pass
            libc.prctl(36, previous.value, 0, 0, 0)


if __name__ == '__main__':
    unittest.main()
