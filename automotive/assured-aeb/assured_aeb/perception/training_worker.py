"""Fresh isolated training4b worker. Standard-library admission precedes every framework import.

Later launcher must use real unshare -rn, explicit sites and -S -s -B; never run this in a runtime/ORT interpreter.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import platform
from pathlib import Path
import re
import resource
import signal
import sys
import sysconfig

from .dataset_consumer import SourceLocations, admit_dataset
from .training_io import absolute, canonical, digest, exact, parse_json, read_regular, record_digest, require, sha
from .training_record import TrainingJob, code_digest as admission_code_digest

STAGE_SCHEMA = "assured-aeb.training-stage4b/1"
CODE_FILES = ("training_network.py", "training_weights.py", "training_loop.py", "training_worker.py")


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


def check_worker_isolation(parent_netns):
    """Require actual parent/self namespace distinction, not equality of supplied integer labels."""
    require(sys.platform == "linux", "training worker requires reviewed Linux namespace facility")
    require(sys.flags.no_site == 1 and sys.flags.no_user_site == 1 and sys.flags.dont_write_bytecode == 1,
            "fresh worker requires -S -s -B")
    require(not any(name.split(".")[0] in {"torch", "numpy", "onnxruntime"} for name in sys.modules),
            "framework already imported before admission")
    require(type(parent_netns) is str and re.fullmatch(r"net:\[[0-9]+\]", parent_netns) is not None, "actual parent netns required")
    parent = Path("/proc") / str(os.getppid()) / "ns"
    require(os.readlink(parent / "net") == parent_netns != os.readlink("/proc/self/ns/net"),
            "fresh unshare network namespace and genuine parent observation required")
    require(os.getuid() == 0 and os.readlink(parent / "user") != os.readlink("/proc/self/ns/user"),
            "fresh unshare -r user namespace required")
    scratch = Path(absolute(os.environ.get("TMPDIR"), "explicit TMPDIR")).resolve()
    require(scratch.is_dir(), "existing explicit scratch directory required")
    for key in ("XDG_CACHE_HOME", "TORCH_HOME", "TORCHINDUCTOR_CACHE_DIR", "TRITON_CACHE_DIR"):
        cache = Path(absolute(os.environ.get(key), key)).resolve()
        require(cache.is_dir() and cache.is_relative_to(scratch), "explicit cache must exist within worker scratch")
    interfaces = [line.split(":", 1)[0].strip() for line in Path("/proc/self/net/dev").read_text().splitlines()[2:]]
    require(interfaces == ["lo"], "training worker network is not isolated to loopback")


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


def run_training(job_bytes, locations_bytes, stage_bytes, *, max_record_bytes, identity_path, lock_path, parent_netns, output_directory):
    """One fresh-process stage; failures never emit candidate publication or resume state."""
    job = TrainingJob.from_bytes(job_bytes, max_record_bytes=max_record_bytes)
    stage = admit_stage(stage_bytes, job, max_record_bytes=max_record_bytes)
    locations = SourceLocations.from_bytes(locations_bytes, max_record_bytes=max_record_bytes)
    check_worker_isolation(parent_netns)
    output = Path(absolute(str(output_directory), "output directory"))
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink(), "fresh output directory with existing parent required")
    namespace = os.readlink("/proc/self/ns/net")
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
        require(os.readlink("/proc/self/ns/net") == namespace
                and not any(name.split(".")[0] == "onnxruntime" for name in sys.modules), "training isolation changed")
        files = {"weights.f32": blob, "weights.json": descriptor, "training-report.json": canonical(report)}
        _write_outputs(output_directory, files, maximum=limits["outputBytes"], disk_limit=limits["diskBytes"])
        return report
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("job", "locations", "stage", "identity", "lock", "parent-netns", "output"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--max-record-bytes", required=True, type=int)
    args = parser.parse_args(argv)
    report = run_training(read_regular(args.job, args.max_record_bytes), read_regular(args.locations, args.max_record_bytes),
                          read_regular(args.stage, args.max_record_bytes), max_record_bytes=args.max_record_bytes,
                          identity_path=args.identity, lock_path=args.lock, parent_netns=args.parent_netns, output_directory=args.output)
    print(canonical(report).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
