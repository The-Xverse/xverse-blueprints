"""Stdlib owning supervisor for explicit training verification; never reports model success."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import time


class AttemptInterrupted(BaseException):
    pass


def expected_nonfinite_refusal(result, error_tail, output):
    """Recognize the pinned Python refusal path, never signal death or an earlier keyword warning."""
    if result.get('capture_complete') is not True or type(result.get('returncode')) is not int or result['returncode'] != 1:
        return False
    if output.exists() or output.is_symlink():
        return False
    lines = error_tail.rstrip().splitlines()
    match = re.fullmatch(r'(?:ValueError|RuntimeError|OverflowError): (.+)', lines[-1]) if lines else None
    return bool(match and any(word in match.group(1).lower() for word in ('nonfinite', 'overflow')))


def _group_exists(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _cleanup(process, term_seconds, kill_seconds):
    result = dict(complete=False, term_sent=False, kill_sent=False, errors=[])
    if process is None:
        result['complete'] = True
        return result
    try:
        if _group_exists(process.pid):
            try:
                os.killpg(process.pid, signal.SIGTERM)
                result['term_sent'] = True
            except ProcessLookupError:
                pass
            end = time.monotonic() + term_seconds
            while _group_exists(process.pid) and time.monotonic() < end:
                process.poll()
                time.sleep(min(0.02, max(0, end-time.monotonic())))
            if _group_exists(process.pid):
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    result['kill_sent'] = True
                except ProcessLookupError:
                    pass
        end = time.monotonic() + kill_seconds
        process.wait(timeout=max(0, end-time.monotonic()))
        while _group_exists(process.pid) and time.monotonic() < end:
            time.sleep(min(0.02, max(0, end-time.monotonic())))
        result['complete'] = not _group_exists(process.pid)
    except Exception as error:
        result['errors'].append(repr(error))
    return result


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def capture_attempt(command, *, environment, cwd, directory, timeout_seconds, term_seconds,
                    kill_seconds, identity_reader, context):
    """Capture a real child outcome. Nonzero exit can be complete capture; caller judges its meaning.

    Only the owned group is supervised. Deliberately escaped sessions are outside this trusted-worker claim.
    Files are exclusive; an I/O failure preserves partial artifacts and propagates failure.
    """
    for value in (timeout_seconds, term_seconds, kill_seconds):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError('explicit positive finite engineering timeout required')
    directory = Path(directory)
    stdout = directory / 'worker.stdout'
    stderr = directory / 'worker.stderr'
    receipt_path = directory / 'worker-execution.json'
    paths = (stdout, stderr, receipt_path)
    if any(path.exists() or path.is_symlink() for path in paths):
        raise FileExistsError('preserve existing attempt diagnostics')
    before = after = None
    process = None
    returncode = None
    timed_out = False
    failure = None
    cleanup = dict(complete=False)
    spawning = False
    pending_signal = None
    old_handlers = {}
    old_mask = None
    signals = {signal.SIGINT, signal.SIGTERM, signal.SIGHUP}
    began = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()

    def interrupted(signum, frame):
        nonlocal pending_signal
        if spawning:
            pending_signal = signum
            return
        raise AttemptInterrupted(signum)

    try:
        # Reserve the receipt before a child can exist; empty/partial artifacts are never success.
        with receipt_path.open('x') as receipt:
            with stdout.open('xb') as out, stderr.open('xb') as err:
                for signum in signals:
                    old_handlers[signum] = signal.signal(signum, interrupted)
                try:
                    before = identity_reader()
                    spawning = True
                    try:
                        process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=out, stderr=err,
                                                   start_new_session=True)
                    finally:
                        spawning = False
                    if pending_signal is not None:
                        raise AttemptInterrupted(pending_signal)
                    try:
                        returncode = process.wait(timeout=timeout_seconds)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                except BaseException as error:
                    failure = repr(error)
                finally:
                    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
                    cleanup = _cleanup(process, term_seconds, kill_seconds)
                    if process is not None:
                        returncode = process.returncode
            try:
                after = identity_reader()
            except Exception as error:
                after = dict(error=repr(error))
                failure = failure or repr(error)
            complete = (type(returncode) is int and not timed_out and failure is None and before == after
                        and cleanup['complete'] is True and not cleanup['term_sent'])
            result = dict(schema='TEST-ONLY-training4b-worker-execution/1', command=list(command),
                          cwd=str(cwd), environment=dict(environment), context=context,
                          inputs_before=before, inputs_after=after, returncode=returncode,
                          timed_out=timed_out, failure=failure, cleanup=cleanup, capture_complete=complete,
                          started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
                          elapsed_seconds=time.monotonic()-began,
                          engineering_bounds=dict(worker_seconds=timeout_seconds, term_seconds=term_seconds,
                                                  kill_seconds=kill_seconds),
                          stdout_sha256=_sha(stdout), stderr_sha256=_sha(stderr),
                          supervisor_sha256=_sha(Path(__file__)), accepted=False, merged=False)
            receipt.write(json.dumps(result, indent=2, sort_keys=True)+'\n')
            receipt.flush()
            os.fsync(receipt.fileno())
        return result
    finally:
        # Cleanup/receipt finalization is bounded and shielded; workers inherit no blocked signal mask.
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        if old_mask is not None:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
