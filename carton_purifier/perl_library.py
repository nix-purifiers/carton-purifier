# SPDX-License-Identifier: MIT
"""Production observation of original Perl library files and their actual SDK.

No catalogs are read at Nix evaluation time. Callers supply immutable source,
SDK and dependency identities; the producer's identity is attached only by the
later projection, avoiding a reference from a derivation to its own identity.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(value):
    path = Path(value)
    if not isinstance(value, str) or not value or path.is_absolute() or "." in value.split("/") or ".." in path.parts or str(path) != value:
        raise ValueError("carton-purifier: noncanonical library-relative path")
    return path


def within(path, roots):
    resolved = Path(path).resolve(strict=True)
    if not any(resolved == root or resolved.is_relative_to(root) for root in roots):
        raise ValueError("carton-purifier: library origin escapes declared closure: " + str(path))
    return resolved


def payload(root, allowed):
    root = Path(root)
    records = []

    def visit(path):
        actual = within(path, allowed)
        info = path.lstat()
        row = {"path": path.relative_to(root).as_posix(), "mode": stat.S_IMODE(info.st_mode) & ~0o222,
               "sha256": None, "target": None, "resolvedOrigin": str(actual)}
        if stat.S_ISLNK(info.st_mode):
            row.update(type="link", target=os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            row.update(type="file", sha256=digest(path.read_bytes()))
        elif stat.S_ISDIR(info.st_mode):
            row["type"] = "directory"
        else:
            raise ValueError("carton-purifier: unsupported library payload type: " + str(path))
        records.append(row)
        # Directory links would make the loader search more files than this
        # explicit tree records. Refuse them rather than silently under-observe.
        if row["type"] == "link" and actual.is_dir():
            raise ValueError("carton-purifier: linked library directories are unsupported")
        if row["type"] == "directory":
            for child in sorted(path.iterdir()):
                visit(child)

    for child in sorted(root.iterdir()):
        if child.name != ".git":
            visit(child)
    return records


def inspect(request, files):
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith("PERL")}
    environment.update(PERL_HASH_SEED="0", PERL_PERTURB_KEYS="0")
    with tempfile.TemporaryDirectory(prefix="perl-library-inspect-") as temporary:
        path = Path(temporary) / "request.json"
        path.write_bytes(canonical({"moduleFiles": files}))
        result = subprocess.run([request["applicationPerl"]["executable"],
                                 str(Path(__file__).with_name("inspect-perl-library.pl")), str(path)],
                                env=environment, text=True, capture_output=True, check=True)
        return json.loads(result.stdout)


def observe(request):
    source = Path(request["sourcePath"]).resolve(strict=True)
    producer = Path(request["producerPath"]).resolve(strict=True)
    allowed = [Path(path).resolve(strict=True) for path in request["allowedRoots"]]
    within(source, allowed)
    within(producer, allowed)
    root_paths = [relative(root) for root in request["roots"]]
    if not root_paths or len(root_paths) != len(set(root_paths)):
        raise ValueError("carton-purifier: explicit nonduplicate library roots required")
    resolved = [within(producer / root, [producer]) for root in root_paths]
    for index, root in enumerate(resolved):
        if not root.is_dir():
            raise ValueError("carton-purifier: library root is not a directory")
        if any(root == other or root.is_relative_to(other) or other.is_relative_to(root)
               for other in resolved[:index]):
            raise ValueError("carton-purifier: overlapping or aliased library roots")
    source_payload = payload(source, allowed)
    source_module_hashes = {row["sha256"] for row in source_payload
                            if row["type"] == "file" and row["path"].endswith(".pm")}
    roots, files, xs_files = [], [], []
    for root in root_paths:
        actual = producer / root
        records = payload(actual, allowed)
        for row in records:
            if row["type"] != "directory" and row["path"].endswith(".pm"):
                actual_hash = digest((actual / row["path"]).read_bytes())
                if actual_hash not in source_module_hashes:
                    raise ValueError("carton-purifier: installed module has no unchanged source payload: " + row["path"])
                files.append({"root": str(root), "path": row["path"], "file": str(actual / row["path"])})
            if row["type"] != "directory" and Path(row["path"]).suffix in {".so", ".dylib", ".dll", ".bundle"}:
                xs_files.append(str((actual / row["path"]).resolve(strict=True)))
        roots.append({"path": str(root), "payload": records, "loadableFiles": []})
    native = inspect(request, files)
    root_map = {row["path"]: row for row in roots}
    packages, lookups = {}, {}
    for module in native["moduleFiles"]:
        key = module["path"]
        if key in lookups:
            raise ValueError("carton-purifier: ambiguous module lookup: " + key)
        lookups[key] = module
        root_map[module["root"]]["loadableFiles"].append({
            "lookup": key, "path": key, "packages": [package["name"] for package in module["packages"]]})
        for package in module["packages"]:
            if package["name"] in packages:
                raise ValueError("carton-purifier: ambiguous declared package: " + package["name"])
            packages[package["name"]] = dict(package, declaredIn=[{"root": module["root"], "path": key}])
    # XS is not assumed compatible from a filename or version. This first
    # observer increment supports pure Perl only; loaded XS proof is integrated
    # in the next increment before the profile accepts native libraries.
    if xs_files:
        raise ValueError("carton-purifier: XS library requires verified native load observation")
    metadata = []
    for name in sorted(request["nativeMetadataPaths"]):
        path = within(name, allowed)
        raw = path.read_bytes()
        value = json.loads(raw)
        metadata.append({"path": str(path), "sha256": digest(raw), "requirements": value.get("prereqs", {})})
    sdk = {"applicationPerl": request["applicationPerl"]["identity"],
           "executable": request["applicationPerl"]["executable"],
           "baseExecutable": str(within(native["baseExecutable"], allowed)),
           "config": native["config"], "runtimeInputs": request["runtimeInputs"],
           "inc": native["inc"], "moduleOrigins": []}
    for module in native["moduleOrigins"]:
        within(module["file"], allowed)
        owners = [entry["identity"] for entry in request["runtimeInputPaths"]
                  if Path(module["file"]).is_relative_to(Path(entry["path"]).resolve(strict=True))]
        if len(owners) != 1:
            raise ValueError("carton-purifier: runtime module has no unique declared input: " + module["file"])
        sdk["moduleOrigins"].append(dict(module, input=owners[0]))
    return {"format": "perl-library-production-v1", "sourceIdentity": request["sourceIdentity"],
            "sourcePayload": source_payload, "producerPath": str(producer), "roots": roots,
            "packages": [packages[name] for name in sorted(packages)], "nativeMetadata": metadata,
            "sdk": sdk, "dependencies": request["dependencies"], "xsLoads": []}


def verify(request, observation):
    if observation.get("format") != "perl-library-production-v1":
        raise ValueError("carton-purifier: unsupported production observation")
    current = observe(request)
    if set(current) != set(observation):
        raise ValueError("carton-purifier: unexpected production observation fields")
    for name in current:
        if canonical(current[name]) != canonical(observation[name]):
            raise ValueError("carton-purifier: stale production observation: " + name)
    return current
