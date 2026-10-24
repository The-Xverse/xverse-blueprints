"""Fresh isolated training4b worker. Standard-library admission precedes every framework import.

Later launcher must use real unshare -rn, explicit sites and -S -s -B; never run this in a runtime/ORT interpreter.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import os
import platform
from pathlib import Path
import re
import resource
import signal
import stat
import sys
import sysconfig

from .dataset_consumer import SourceLocations, admit_dataset
from .training_io import absolute, canonical, digest, exact, parse_json, read_regular, record_digest, require, sha
from .training_record import TrainingJob, code_digest as admission_code_digest

STAGE_SCHEMA = "assured-aeb.training-stage4b/1"
CODE_FILES = ("training_network.py", "training_weights.py", "training_loop.py", "training_worker.py")
PARENT_NAMESPACE_SCHEMA = "assured-aeb.parent-namespace-proof/1"
# Reviewed Linux x86_64 UAPI: nsfs.h _IO(0xb7,3), asm-generic/ioctl.h and sched.h.
NS_GET_NSTYPE = 0xB703
NAMESPACE_TYPES = {"net": 0x40000000, "user": 0x10000000}


def _namespace_abi():
    require(sys.platform == "linux" and platform.machine() == "x86_64", "reviewed Linux x86_64 namespace ABI required")


def namespace_identity(fd):
    """Typed kernel namespace identity, never a supplied namespace string or parent proc lookup."""
    _namespace_abi()
    require(type(fd) is int and fd >= 3, "nonstandard namespace descriptor required")
    info = os.fstat(fd)
    require(stat.S_ISREG(info.st_mode) and fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY,
            "read-only namespace descriptor required")
    kind = fcntl.ioctl(fd, NS_GET_NSTYPE)
    require(kind in NAMESPACE_TYPES.values(), "network/user namespace descriptor required")
    return kind, info.st_dev, info.st_ino


@contextmanager
def captured_parent_namespaces():
    """Original launcher owns both pre-unshare handles through capture/cleanup/identity receipt."""
    _namespace_abi()
    # Follow these genuine own procfs magic links intentionally; owned FileIO closes partial acquisition.
    with open("/proc/self/ns/net", "rb", buffering=0) as net, open("/proc/self/ns/user", "rb", buffering=0) as user:
        handles = {"net": net, "user": user}

        def observe():
            result = {"schema": PARENT_NAMESPACE_SCHEMA, "parentPid": os.getpid()}
            for name, handle in handles.items():
                fd = handle.fileno()
                kind, device, inode = namespace_identity(fd)
                reference = os.readlink("/proc/self/ns/" + name)
                require(kind == NAMESPACE_TYPES[name] and reference == f"{name}:[{inode}]"
                        and not os.get_inheritable(fd), "original parent namespace changed or fd inheritable")
                result[name] = dict(fd=fd, device=device, inode=inode, reference=reference)
            return result

        original = observe()
        yield original, (net.fileno(), user.fileno()), observe


class ParentNamespaceProof:
    """Owning child copies of exactly the declared typed namespace descriptors; no arbitrary-range cleanup."""

    def __init__(self):
        raise TypeError("namespace proof must come from descriptor adoption")

    @classmethod
    def adopt(cls, data, *, max_record_bytes):
        record = parse_json(data, max_bytes=max_record_bytes, canonical_required=True)
        exact(record, {"schema", "parentPid", "net", "user"}, "parent namespace proof")
        require(record["schema"] == PARENT_NAMESPACE_SCHEMA and type(record["parentPid"]) is int
                and record["parentPid"] > 0, "actual original parent PID required")
        for name in NAMESPACE_TYPES:
            value = record[name]
            exact(value, {"fd", "device", "inode", "reference"}, name + " namespace proof")
            require(type(value["fd"]) is int and value["fd"] >= 3, "nonstandard proof fd required")
            require(type(value["device"]) is int and value["device"] >= 0
                    and type(value["inode"]) is int and value["inode"] > 0, "actual namespace identity required")
            require(value["reference"] == f"{name}:[{value['inode']}]", "actual namespace reference required")
        require(record["net"]["fd"] != record["user"]["fd"], "distinct namespace descriptors required")
        proof = cls.__new__(cls)
        proof._record, proof._handles, proof._closed = record, {}, False
        errors = []
        try:
            # Inspect/adopt both before opening any self fd: closed proof numbers can never be recycled/closed.
            for name in NAMESPACE_TYPES:
                value = record[name]
                try:
                    identity = namespace_identity(value["fd"])
                    # Only a real typed namespace is adopted. Arbitrary file/pipe/std sentinels remain caller-owned.
                    handle = os.fdopen(value["fd"], "rb", buffering=0)
                    proof._handles[name] = handle
                    os.set_inheritable(handle.fileno(), False)
                    require(identity == (NAMESPACE_TYPES[name], value["device"], value["inode"]),
                            "inherited namespace differs from original parent observation")
                except (OSError, ValueError) as error:
                    errors.append(error)
            if errors:
                raise ValueError("parent namespace descriptor admission failed") from errors[0]
            return proof
        except BaseException:
            proof.close()
            raise

    def validate(self):
        require(not self._closed and set(self._handles) == set(NAMESPACE_TYPES), "live adopted namespace proof required")
        require(os.getppid() == self._record["parentPid"], "original no-fork launcher parent changed")
        for name, handle in self._handles.items():
            value = self._record[name]
            require(namespace_identity(handle.fileno()) == (NAMESPACE_TYPES[name], value["device"], value["inode"])
                    and not os.get_inheritable(handle.fileno()), "adopted namespace proof changed")

    def close(self):
        if not self._closed:
            self._closed = True
            handles, self._handles = self._handles, {}
            errors = []
            for handle in handles.values():
                try:
                    handle.close()
                except OSError as error:
                    errors.append(error)
            if errors:
                raise errors[0]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def _self_namespace_snapshot():
    identities = []
    for name in NAMESPACE_TYPES:
        with open("/proc/self/ns/" + name, "rb", buffering=0) as handle:
            identity = namespace_identity(handle.fileno())
            require(identity[0] == NAMESPACE_TYPES[name] and not os.get_inheritable(handle.fileno()), "self namespace type changed")
            identities.append(identity)
    require(os.getuid() == 0, "fresh unshare -r user namespace required")
    interfaces = [line.split(":", 1)[0].strip() for line in Path("/proc/self/net/dev").read_text().splitlines()[2:]]
    require(interfaces == ["lo"], "training worker network is not isolated to loopback")
    return tuple(identities)


def code_digest():
    root = Path(__file__).resolve().parent
    return record_digest([{"file": name, "sha256": sha((root / name).read_bytes())} for name in CODE_FILES])


def admit_stage(data, job, *, max_record_bytes):
    stage = parse_json(data, max_bytes=max_record_bytes, canonical_required=True)
    exact(stage, {"schema", "jobSha256", "sourceClosureSha256"}, "stage4b")
    require(stage["schema"] == STAGE_SCHEMA and stage["jobSha256"] == job.sha256, "stage4b schema/job mismatch")
    require(digest(stage["sourceClosureSha256"], "stage4b source") == code_digest(), "stage4b source closure mismatch")
    return stage


def _sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _tree(root, *, skip=()):
    """Exact genuine compat identity algorithm; symlink entries bind targets, never followed."""
    h, count = hashlib.sha256(), 0
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in skip and os.path.join(base, d) not in skip)
        links = [d for d in os.listdir(base) if os.path.islink(os.path.join(base, d)) and d not in files]
        for name in sorted(files + links):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root)
            entry = "link:" + os.readlink(path) if os.path.islink(path) else _sha_file(path)
            h.update(f"{rel}\0{entry}\n".encode())
            count += 1
    return {"sha256": h.hexdigest(), "entries": count}


def check_worker_isolation(parent_namespace_proof):
    """Require genuine typed parent/self distinction and close proof copies before frameworks, even on refusal."""
    require(type(parent_namespace_proof) is ParentNamespaceProof, "mandatory adopted parent namespace proof required")
    try:
        _namespace_abi()
        require(sys.flags.no_site == 1 and sys.flags.no_user_site == 1 and sys.flags.dont_write_bytecode == 1,
                "fresh worker requires -S -s -B")
        require(not any(name.split(".")[0] in {"torch", "numpy", "onnxruntime"} for name in sys.modules),
                "framework already imported before admission")
        parent_namespace_proof.validate()
        own = _self_namespace_snapshot()
        for name, identity in zip(NAMESPACE_TYPES, own):
            value = parent_namespace_proof._record[name]
            require(identity[1:] != (value["device"], value["inode"]), "fresh unshare net AND user namespaces required")
        scratch = Path(absolute(os.environ.get("TMPDIR"), "explicit TMPDIR")).resolve()
        require(scratch.is_dir(), "existing explicit scratch directory required")
        for key in ("XDG_CACHE_HOME", "TORCH_HOME", "TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR"):
            cache = Path(absolute(os.environ.get(key), key)).resolve()
            require(cache.is_dir() and cache.is_relative_to(scratch), "explicit cache must exist within worker scratch")
        return own
    finally:
        parent_namespace_proof.close()


def check_import_paths(sites):
    from xverse_compat.inference import preprocess as shared
    stdlib = Path(sysconfig.get_paths()["stdlib"]).resolve()
    approved = {stdlib, stdlib / "lib-dynload", stdlib.parent / f"python{sys.version_info.major}{sys.version_info.minor}.zip",
                Path(__file__).resolve().parents[2], Path(shared.__file__).resolve().parents[2], *sites}
    require(all(type(path) is str and Path(path).is_absolute() and Path(path).resolve() in approved for path in sys.path),
            "unexpected/relative Python import search path")


def verify_environment(job, identity_path, lock_path):
    """Verify pinned actual bytes/trees and import search origins with no framework import."""
    record = job.record()
    expected = record["environments"]["training"]
    maximum = record["environments"]["limits"]["sourceBytes"]
    identity_bytes = read_regular(absolute(str(identity_path), "identity path"), maximum)
    lock_bytes = read_regular(absolute(str(lock_path), "lock path"), maximum)
    require(sha(identity_bytes) == expected["identitySha256"] and sha(lock_bytes) == expected["lockSha256"], "training identity/lock digest mismatch")
    identity = parse_json(identity_bytes, max_bytes=maximum)
    require(identity.get("schema") == "xverse-compat.training-env-record/1" and type(identity.get("importReturnCode")) is int
            and identity["importReturnCode"] == 0, "genuine successful compat training identity required")
    require(identity["lock"]["sha256"] == expected["lockSha256"]
            and identity["lock"]["repositoryRevision"] == expected["sourceRevision"], "training lock source identity mismatch")
    interpreter = identity["interpreter"]
    require(Path(sys.executable).resolve() == Path(expected["python"]).resolve() == Path(interpreter["path"]).resolve(),
            "actual interpreter differs from admitted one")
    require(_sha_file(sys.executable) == interpreter["sha256"] and sys.version.split()[0] == interpreter["version"], "interpreter bytes/version mismatch")
    require(Path(sysconfig.get_paths()["stdlib"]).resolve() == Path(interpreter["stdlib"]).resolve(), "stdlib location mismatch")
    stdlib = interpreter["stdlib"]
    require(_tree(stdlib, skip=("__pycache__", os.path.join(stdlib, "site-packages"))) == interpreter["stdlibTree"], "stdlib tree mismatch")
    if interpreter["libpython"] is not None:
        lib = interpreter["libpython"]
        libdir, libname = sysconfig.get_config_var("LIBDIR"), sysconfig.get_config_var("INSTSONAME") or sysconfig.get_config_var("LDLIBRARY")
        require(libdir is not None and libname is not None and Path(libdir, libname).resolve() == Path(lib["path"]).resolve()
                and _sha_file(lib["path"]) == lib["sha256"], "libpython mismatch")
    require(list(platform.libc_ver()) == identity["glibc"], "training glibc identity mismatch")
    cpu = {}
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        key, _, value = line.partition(":")
        if key.strip() in ("model name", "flags") and key.strip() not in cpu:
            cpu[key.strip()] = value.strip()
    require(cpu == identity["cpu"], "training CPU identity mismatch")
    sites = [Path(path).resolve() for path in expected["sites"]]
    require(sites == [Path(identity["sitePackages"]).resolve()], "training identity must bind every admitted site")
    actual_sites = [Path(path).resolve() for path in sys.path if path and "site-packages" in Path(path).parts]
    require(actual_sites == sites, "unexpected/missing explicit site-packages search path")
    check_import_paths(sites)
    site = Path(identity["sitePackages"])
    venv = site.parents[2]
    require(_tree(site) == identity["sitePackagesTree"] and _tree(venv) == identity["venvTree"], "training site/venv tree mismatch")
    require(not any(p.name == "__pycache__" or p.suffix == ".pyc" for p in venv.rglob("*")), "bytecode in pinned training environment")
    versions = {}
    for line in lock_bytes.decode().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.match(r"([A-Za-z0-9_-]+)==([^\s]+)\s", line)
        require(match is not None and match.group(1) not in versions and "--hash=sha256:" in line, "unsupported/duplicate unhashed lock entry")
        versions[match.group(1)] = match.group(2)
    require("torch" in versions and "numpy" in versions and versions["torch"].endswith("+cpu")
            and versions["numpy"] == record["preprocessing"]["numpyVersion"], "CPU torch/shared numpy lock required")
    for name in ("torch", "numpy"):
        spec = importlib.util.find_spec(name)
        require(spec is not None and spec.origin is not None and Path(spec.origin).resolve().is_relative_to(sites[0]), "framework resolves outside admitted site")
    return {"identitySha256": expected["identitySha256"], "lockSha256": expected["lockSha256"],
            "sourceRevision": expected["sourceRevision"], "versions": versions}


def _limit(kind, value):
    _, hard = resource.getrlimit(kind)
    effective = value if hard == resource.RLIM_INFINITY else min(value, hard)
    resource.setrlimit(kind, (effective, effective))


def _expired(signum, frame):
    raise TimeoutError("training worker exceeded admitted engineering timeout")


def _write_outputs(directory, files, *, maximum, disk_limit):
    require(sum(len(data) for data in files.values()) <= min(maximum, disk_limit), "aggregate training output exceeds byte limits")
    root = Path(absolute(str(directory), "output directory"))
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    created = []
    try:
        for name, data in files.items():
            path = root / name
            with path.open("xb") as handle:
                created.append(path)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        for path in reversed(created):
            path.unlink()
        root.rmdir()
        raise


def run_training(job_bytes, locations_bytes, stage_bytes, *, max_record_bytes, identity_path, lock_path, parent_namespace_proof, output_directory):
    """One fresh-process stage; failures never emit candidate publication or resume state."""
    job = TrainingJob.from_bytes(job_bytes, max_record_bytes=max_record_bytes)
    stage = admit_stage(stage_bytes, job, max_record_bytes=max_record_bytes)
    locations = SourceLocations.from_bytes(locations_bytes, max_record_bytes=max_record_bytes)
    namespace = check_worker_isolation(parent_namespace_proof)
    output = Path(absolute(str(output_directory), "output directory"))
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink(), "fresh output directory with existing parent required")
    limits = job.record()["environments"]["limits"]
    _limit(resource.RLIMIT_AS, limits["memoryBytes"])
    _limit(resource.RLIMIT_FSIZE, limits["outputBytes"])
    signal.signal(signal.SIGALRM, _expired)
    signal.setitimer(signal.ITIMER_REAL, limits["workerTimeoutS"])
    try:
        dataset = admit_dataset(job, locations)
        environment = verify_environment(job, identity_path, lock_path)
        # All job/source/dataset/stage/namespace/environment checks precede these imports.
        import numpy
        import torch
        from xverse_compat.inference import preprocess as shared
        require(numpy.__version__ == environment["versions"]["numpy"] and torch.__version__ == environment["versions"]["torch"], "actual framework version mismatch")
        site = Path(job.record()["environments"]["training"]["sites"][0]).resolve()
        require(Path(numpy.__file__).resolve().is_relative_to(site) and Path(torch.__file__).resolve().is_relative_to(site), "loaded framework origin mismatch")
        require(torch.version.cuda is None and not torch.cuda.is_available() and "onnxruntime" not in sys.modules, "CPU-only separate training worker required")
        opt = job.record()["optimisation"]
        torch.set_num_threads(opt["intraOpThreads"])
        torch.set_num_interop_threads(opt["interOpThreads"])
        torch.use_deterministic_algorithms(opt["deterministicAlgorithms"], warn_only=False)
        torch.manual_seed(opt["seeds"]["torch"])
        numpy.random.seed(opt["seeds"]["numpy"])
        require(torch.get_num_threads() == opt["intraOpThreads"] and torch.get_num_interop_threads() == opt["interOpThreads"]
                and torch.are_deterministic_algorithms_enabled(), "requested determinism/thread settings unavailable")
        from .training_loop import fit
        from .training_weights import decode_weights
        stage_sha256 = sha(stage_bytes)
        _, descriptor, blob, report = fit(job, dataset, stage_sha256, torch=torch, numpy=numpy, shared=shared)
        decode_weights(descriptor, blob, job, stage_sha256=stage_sha256)
        report.update(stageSourceClosureSha256=stage["sourceClosureSha256"], environment=environment,
                      torchVersion=torch.__version__, numpyVersion=numpy.__version__)
        require(code_digest() == stage["sourceClosureSha256"]
                and admission_code_digest() == job.record()["identity"]["codeClosureSha256"]
                and shared.code_sha256() == job.record()["preprocessing"]["codeSha256"], "source changed during training")
        require(verify_environment(job, identity_path, lock_path) == environment, "environment changed during training")
        require(_self_namespace_snapshot() == namespace
                and not any(name.split(".")[0] == "onnxruntime" for name in sys.modules), "training isolation changed")
        files = {"weights.f32": blob, "weights.json": descriptor, "training-report.json": canonical(report)}
        _write_outputs(output_directory, files, maximum=limits["outputBytes"], disk_limit=limits["diskBytes"])
        return report
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("job", "locations", "stage", "identity", "lock", "parent-namespace-proof", "output"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--max-record-bytes", required=True, type=int)
    args = parser.parse_args(argv)
    with ParentNamespaceProof.adopt(args.parent_namespace_proof.encode(), max_record_bytes=args.max_record_bytes) as proof:
        report = run_training(read_regular(args.job, args.max_record_bytes), read_regular(args.locations, args.max_record_bytes),
                              read_regular(args.stage, args.max_record_bytes), max_record_bytes=args.max_record_bytes,
                              identity_path=args.identity, lock_path=args.lock, parent_namespace_proof=proof, output_directory=args.output)
    print(canonical(report).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
