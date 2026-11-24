# SPDX-License-Identifier: MIT
"""Bind native MakeMaker PM entries to the actual native install-copy events."""
from pathlib import Path, PurePosixPath
import re
import sys

from perl_library import canonical, digest, relative, within

FORMAT = "perl-makemaker-install-map-v1"
VARIABLES = {"INST_LIB", "INST_ARCHLIB", "INST_LIBDIR", "INST_ARCHLIBDIR", "INSTALL_BASE",
             "INSTALLDIRS", "INSTALLSITELIB", "INSTALLSITEARCH", "INSTALLPRIVLIB", "INSTALLARCHLIB", "MAKEFILE"}


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("carton-purifier: unsupported " + label + " fields")


def sha(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("carton-purifier: invalid native mapping SHA256")
    return value


def rel(value, dot=False):
    if dot and value == ".":
        return Path(".")
    return relative(value)


def join_native(cwd, value):
    rel(cwd, dot=True)
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('carton-purifier: unsupported native path')
    if PurePosixPath(value).is_absolute() or '@build@' in value or '@producer@' in value:
        raise ValueError('carton-purifier: unbound absolute or root token in native path')
    parts = [] if cwd == '.' else cwd.split('/')
    for component in value.split('/'):
        if component in ('', '.'):
            continue
        if component == '..':
            if not parts:
                raise ValueError('carton-purifier: native path escapes build root')
            parts.pop()
        else:
            parts.append(component)
    if not parts:
        raise ValueError('carton-purifier: native module path names build root')
    return '/'.join(parts)


def expand(value, variables):
    if not isinstance(value, str):
        raise ValueError("carton-purifier: native PM destination is not a string")
    seen = set()
    for _ in range(32):
        if value in seen:
            raise ValueError("carton-purifier: cyclic native PM variable")
        seen.add(value)
        matches = list(re.finditer(r"\$\(([A-Z_][A-Z_0-9]*)\)", value))
        if not matches:
            if "$" in value or "`" in value:
                raise ValueError("carton-purifier: unsupported native PM expression")
            return value
        for match in reversed(matches):
            name = match[1]
            replacement = variables.get(name)
            if not isinstance(replacement, str):
                raise ValueError("carton-purifier: undefined native PM variable: " + name)
            value = value[:match.start()] + replacement + value[match.end():]
    raise ValueError("carton-purifier: excessive native PM expansion")


def owner(request, path):
    actual = Path(path).resolve(strict=True)
    owners = [entry["identity"] for entry in request["runtimeInputPaths"]
              if actual.is_relative_to(Path(entry["path"]).resolve(strict=True))]
    if len(owners) != 1:
        raise ValueError("carton-purifier: native mapping SDK has no unique declared owner")
    return owners[0]


def native_sources(request, records):
    output = {}
    for item in records:
        exact(item, ["module", "file", "sha256", "input"], "native SDK source")
        if re.fullmatch(r"ExtUtils/(?:MakeMaker|Install|MM_[A-Za-z_0-9]+)\.pm", item["module"]) is None:
            raise ValueError("carton-purifier: unsupported native mapping SDK module")
        file = Path(item["file"])
        if not file.as_posix().endswith("/" + item["module"]):
            raise ValueError("carton-purifier: native mapping SDK module path differs")
        if owner(request, file) != item["input"] or digest(file.read_bytes()) != sha(item["sha256"]):
            raise ValueError("carton-purifier: native mapping SDK source differs")
        if item["module"] in output:
            raise ValueError("carton-purifier: duplicate native SDK source")
        output[item["module"]] = item
    if not {"ExtUtils/MakeMaker.pm", "ExtUtils/Install.pm"}.issubset(output) or not any(k.startswith("ExtUtils/MM_") for k in output):
        raise ValueError("carton-purifier: incomplete native mapping SDK sources")
    return [output[key] for key in sorted(output)]


def adapter_identity(sources):
    tools = Path(__file__).parent
    files = ["maker_mapping.py", "perl_library.py", "Carton/Purifier/MakeMaker.pm"]
    return digest(canonical({"tools": {name: digest((tools / name).read_bytes()) for name in files},
                             "nativeSources": sources}))


def root_context(request):
    source = Path(request["sourcePath"]).resolve(strict=True)
    producer = Path(request["producerPath"]).resolve(strict=True)
    if set(request["sourceRoots"]) != set(request["roots"]):
        raise ValueError("carton-purifier: native source root associations differ")
    roots = {}
    source_roots = []
    for name in request["roots"]:
        root = within(producer / rel(name), [producer])
        authored_root = within(source / rel(request["sourceRoots"][name], dot=True), [source])
        if not root.is_dir() or not authored_root.is_dir():
            raise ValueError("carton-purifier: native lookup root is not a directory")
        if any(root == other or root.is_relative_to(other) or other.is_relative_to(root) for other in roots.values()):
            raise ValueError("carton-purifier: ambiguous native installed root")
        if any(authored_root == other or authored_root.is_relative_to(other) or other.is_relative_to(authored_root) for other in source_roots):
            raise ValueError("carton-purifier: ambiguous native source lookup root")
        roots[name] = root
        source_roots.append(authored_root)
    return source, producer, roots


def mapping_from_evidence(request, evidence):
    exact(evidence, ["format", "sourceIdentity", "applicationPerlIdentity", "adapterIdentity", "nativeSources", "makers", "copies"], "native mapping evidence")
    if evidence["format"] != FORMAT or evidence["sourceIdentity"] != request["sourceIdentity"] or evidence["applicationPerlIdentity"] != request["applicationPerl"]["identity"]:
        raise ValueError("carton-purifier: cross-source or SDK native mapping evidence")
    sources = native_sources(request, evidence["nativeSources"])
    if evidence["adapterIdentity"] != adapter_identity(sources):
        raise ValueError("carton-purifier: stale native mapping adapter")
    source, producer, roots = root_context(request)
    copies = evidence["copies"]
    seen_targets = set()
    for event in copies:
        exact(event, ["buildSource", "producerDestination", "sourceSha256", "destinationSha256", "dryRun"], "native copy")
        rel(event["buildSource"])
        target = within(producer / rel(event["producerDestination"]), [producer])
        if event["producerDestination"] in seen_targets:
            raise ValueError("carton-purifier: ambiguous native copy destination")
        seen_targets.add(event["producerDestination"])
        if event["dryRun"] is not False or sha(event["sourceSha256"]) != sha(event["destinationSha256"]):
            raise ValueError("carton-purifier: native copy bytes differ or dry run")
        if digest(target.read_bytes()) != event["destinationSha256"]:
            raise ValueError("carton-purifier: native installed mapping payload changed")
    if copies != sorted(copies, key=lambda row: (row["producerDestination"], row["buildSource"], canonical(row))):
        raise ValueError("carton-purifier: noncanonical native copy order")
    files, destinations, maker_ids = [], set(), set()
    for mm_index, maker in enumerate(evidence["makers"]):
        exact(maker, ["sourceCwd", "pm", "variables", "canonicalMakefileSha256"], "native maker")
        cwd = rel(maker["sourceCwd"], dot=True)
        sha(maker["canonicalMakefileSha256"])
        maker_id = (maker["sourceCwd"], canonical(maker))
        if maker_id in maker_ids:
            raise ValueError("carton-purifier: ambiguous native maker identity")
        maker_ids.add(maker_id)
        exact(maker["variables"], VARIABLES, "native MM variables")
        if any(value is not None and not isinstance(value, str) for value in maker["variables"].values()):
            raise ValueError("carton-purifier: unsupported native MM variable value")
        if not isinstance(maker["pm"], dict):
            raise ValueError("carton-purifier: invalid native PM map")
        for authored, expression in sorted(maker["pm"].items()):
            if not isinstance(authored, str):
                raise ValueError("carton-purifier: invalid native PM source")
            if not authored.endswith(".pm"):
                continue
            original_relative = join_native(maker["sourceCwd"], authored)
            original = within(source / rel(original_relative), [source])
            blib = join_native(maker["sourceCwd"], expand(expression, maker["variables"]))
            matches = [(index, copy) for index, copy in enumerate(copies) if copy["buildSource"] == blib]
            if len(matches) != 1:
                raise ValueError("carton-purifier: native PM has no unique install copy")
            copy_index, event = matches[0]
            target = within(producer / event["producerDestination"], [producer])
            owners = [(name, root) for name, root in roots.items() if target.is_relative_to(root)]
            if len(owners) != 1:
                raise ValueError("carton-purifier: native PM target has no unique installed root")
            root, root_path = owners[0]
            lookup = target.relative_to(root_path).as_posix()
            within(original, [(source / request["sourceRoots"][root]).resolve(strict=True)])
            if (root, lookup) in destinations:
                raise ValueError("carton-purifier: ambiguous native PM destination")
            destinations.add((root, lookup))
            source_hash = digest(original.read_bytes())
            if source_hash != event["sourceSha256"]:
                raise ValueError("carton-purifier: native source/blib/install bytes differ")
            files.append({"root": root, "lookup": lookup, "sourcePath": original_relative,
                          "sourceSha256": source_hash, "installedSha256": event["destinationSha256"],
                          "mmInvocation": mm_index, "installCopyEvent": copy_index})
    if evidence["makers"] != sorted(evidence["makers"], key=lambda row: (row["sourceCwd"], canonical(row))):
        raise ValueError("carton-purifier: noncanonical native maker order")
    if not files:
        raise ValueError("carton-purifier: native mapping contains no source modules")
    mapping = {key: evidence[key] for key in ("format", "sourceIdentity", "applicationPerlIdentity", "adapterIdentity", "nativeSources")}
    mapping.update(canonicalEvidenceSha256=digest(canonical(evidence)), files=files)
    return mapping


def verify(request, mapping, evidence):
    expected = mapping_from_evidence(request, evidence)
    if canonical(expected) != canonical(mapping):
        raise ValueError("carton-purifier: stale or altered native module mapping")
    return expected


def validate(request, events, build_root):
    source, producer, _ = root_context(request)
    build = Path(build_root).resolve(strict=True)
    makers, copies, sdk = [], [], {}

    def normalize(value):
        if value is None:
            return value
        if not isinstance(value, str):
            raise ValueError("carton-purifier: unsupported captured native MM value")
        for root, token in [(build, "@build@"), (producer, "@producer@")]:
            if value == str(root) or value.startswith(str(root) + "/"):
                return token + value[len(str(root)):]
        return value

    for event in events:
        shared = ["kind", "cwd", "baseExecutable", "nativeSources", "context"]
        fields = shared + (["pm", "variables", "makerVersion", "makefileSha256"] if event.get("kind") == "native-MM-flush"
                           else ["from", "to", "dryRun", "sourceSha256", "destinationSha256"])
        exact(event, fields, "captured native event")
        if event["context"] not in {"void", "list", "scalar"} or str(Path(event["baseExecutable"]).resolve(strict=True)) != request["observedBaseExecutable"]:
            raise ValueError("carton-purifier: captured native application SDK/context differs")
        for record in event["nativeSources"]:
            exact(record, ["module", "file", "sha256"], "captured SDK source")
            owned = dict(record, input=owner(request, record["file"]))
            if record["module"] in sdk and sdk[record["module"]] != owned:
                raise ValueError("carton-purifier: inconsistent captured SDK source")
            sdk[record["module"]] = owned
        cwd = within(event["cwd"], [build])
        if event["kind"] == "native-MM-flush":
            exact(event["variables"], VARIABLES, "captured MM variables")
            makefile = within(cwd / rel(event["variables"]["MAKEFILE"]), [build])
            raw = makefile.read_bytes()
            if digest(raw) != sha(event["makefileSha256"]):
                raise ValueError("carton-purifier: native Makefile changed after capture")
            normalized = raw.replace(str(build).encode(), b"@build@").replace(str(producer).encode(), b"@producer@")
            normalized_pm = {}
            for authored, expression in event["pm"].items():
                source_name, target_expression = normalize(authored), normalize(expression)
                if source_name in normalized_pm:
                    raise ValueError("carton-purifier: ambiguous normalized native PM source")
                normalized_pm[source_name] = target_expression
                if not authored.endswith(".pm"):
                    continue
                if Path(authored).is_absolute():
                    raise ValueError("carton-purifier: absolute native PM source is unsupported")
                source_relative = join_native(cwd.relative_to(build).as_posix(), source_name)
                built_original = within(cwd / Path(authored), [build])
                if built_original.relative_to(build).as_posix() != source_relative:
                    raise ValueError("carton-purifier: native source path has a physical alias")
                original = within(source / source_relative, [source])
                expanded = expand(expression, event["variables"])
                if Path(expanded).is_absolute():
                    raise ValueError("carton-purifier: absolute native blib path is unsupported")
                blib_relative = join_native(cwd.relative_to(build).as_posix(), normalize(expanded))
                blib = within(cwd / Path(expanded), [build])
                if blib.relative_to(build).as_posix() != blib_relative:
                    raise ValueError("carton-purifier: native blib path has a physical alias")
                if digest((cwd / authored).read_bytes()) != digest(original.read_bytes()) or digest(blib.read_bytes()) != digest(original.read_bytes()):
                    raise ValueError("carton-purifier: captured source/blib bytes differ")
            makers.append({"sourceCwd": cwd.relative_to(build).as_posix(), "pm": normalized_pm,
                           "variables": {key: normalize(value) for key, value in event["variables"].items()},
                           "canonicalMakefileSha256": digest(normalized)})
        elif event["kind"] == "native-install-copy":
            origin = within(event["from"], [build])
            target = within(event["to"], [producer])
            if digest(origin.read_bytes()) != sha(event["sourceSha256"]) or digest(target.read_bytes()) != sha(event["destinationSha256"]):
                raise ValueError("carton-purifier: captured install copy changed")
            copies.append({"buildSource": origin.relative_to(build).as_posix(), "producerDestination": target.relative_to(producer).as_posix(),
                           "sourceSha256": event["sourceSha256"], "destinationSha256": event["destinationSha256"], "dryRun": event["dryRun"]})
        else:
            raise ValueError("carton-purifier: unsupported captured native event")
    sources = native_sources(request, [sdk[key] for key in sorted(sdk)])
    targets = [row["producerDestination"] for row in copies]
    maker_ids = [(row["sourceCwd"], canonical(row)) for row in makers]
    if len(set(targets)) != len(targets):
        raise ValueError("carton-purifier: ambiguous native copy destination")
    if len(set(maker_ids)) != len(maker_ids):
        raise ValueError("carton-purifier: ambiguous native maker identity")
    # Native File::Find/copy traversal order is not semantic and can vary between
    # identical builds. Assign provenance indices only after canonical ordering.
    makers.sort(key=lambda row: (row["sourceCwd"], canonical(row)))
    copies.sort(key=lambda row: (row["producerDestination"], row["buildSource"], canonical(row)))
    for event in events:
        print(canonical(event).decode(), file=sys.stderr)
    evidence = {"format": FORMAT, "sourceIdentity": request["sourceIdentity"],
                "applicationPerlIdentity": request["applicationPerl"]["identity"], "adapterIdentity": adapter_identity(sources),
                "nativeSources": sources, "makers": makers, "copies": copies}
    return mapping_from_evidence(request, evidence), evidence
