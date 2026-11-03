# SPDX-License-Identifier: MIT
"""Capture native Carton selections and the exact CPAN distribution bytes."""

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .common import atomic, digest, run


def relative(name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("inputs must be relative project paths")
    return path


def capture(
    root, companion, snapshot, native, metadata_perl, input_names, update=False
):
    inputs = sorted(set(["cpanfile", *input_names]))
    with tempfile.TemporaryDirectory(prefix="carton-lock-") as temporary:
        scratch = Path(temporary)
        project = scratch / "project"
        project.mkdir()
        records = {}
        for name in inputs:
            path = relative(name)
            source = root / path
            if not source.resolve().is_relative_to(root.resolve()):
                raise ValueError("inputs must stay within the project")
            content = source.read_bytes()
            destination = project / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            records[name] = {"content": content.decode(), "sha256": digest(content)}
        if snapshot.exists():
            shutil.copyfile(snapshot, project / "cpanfile.snapshot")
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(
                ("CARTON_PURIFIER_", "PERL", "NIX_CFLAGS", "NIX_LDFLAGS")
            )
            and k
            not in {
                "CC",
                "CXX",
                "LD",
                "AS",
                "AR",
                "RANLIB",
                "CFLAGS",
                "CPPFLAGS",
                "CXXFLAGS",
                "LDFLAGS",
                "CPATH",
                "C_INCLUDE_PATH",
                "CPLUS_INCLUDE_PATH",
                "LIBRARY_PATH",
                "PKG_CONFIG_PATH",
                "PKG_CONFIG_LIBDIR",
            }
        }
        env.update(
            {
                "HOME": str(scratch / "home"),
                "PERL_CPANM_HOME": str(scratch / "cpanm"),
                "PERL_CARTON_PATH": str(project / "local"),
                "PERL_CARTON_CPANFILE": str(project / "cpanfile"),
                "PERL_CARTON_MIRROR": "https://cpan.metacpan.org",
            }
        )
        Path(env["HOME"]).mkdir()
        run([native, "install"], cwd=project, env=env)
        if update:
            run([native, "update"], cwd=project, env=env)
        selected = project / "cpanfile.snapshot"
        data = json.loads(
            run(
                [metadata_perl, Path(__file__).with_name("snapshot.pl"), selected],
                stdout=subprocess.PIPE,
                text=True,
                env=env,
            ).stdout
        )
        if data["formatVersion"] != "1.0":
            raise ValueError("unsupported native Carton snapshot format")
        entries = []
        for distribution in data["distributions"]:
            path = distribution["pathname"]
            if not re.fullmatch(
                r"[A-Za-z0-9]/[A-Za-z0-9]{2}/[A-Za-z0-9_-]+/[A-Za-z0-9_.+-]+", path
            ):
                raise ValueError(
                    "only CPAN distribution archives are prepared: " + path
                )
            archive = project / "local/cache/authors/id" / path
            if not archive.is_file():
                raise ValueError(
                    "native Carton did not retain selected source archive: " + path
                )
            sri = (
                "sha256-"
                + base64.b64encode(bytes.fromhex(digest(archive.read_bytes()))).decode()
            )
            entries.append(
                {
                    "path": "authors/id/" + path,
                    "url": "https://cpan.metacpan.org/authors/id/" + path,
                    "hash": sri,
                    "mirrors": ["https://backpan.perl.org/authors/id/" + path],
                }
            )
        native_bytes = selected.read_bytes()
        tool_versions = {
            key: str(value).lstrip("v")
            for key, value in data["toolVersions"].items()
            if key != "archname"
        }
        tool_versions.update(
            {
                "gcc": os.environ["CARTON_PURIFIER_GCC_VERSION"],
                "sdk": os.environ["CARTON_PURIFIER_SDK_VERSION"],
            }
        )
        result = {
            "schemaVersion": 1,
            "purifier": "carton",
            "toolVersions": tool_versions,
            "inputs": records,
            "snapshot": {"sha256": digest(native_bytes)},
            "distributions": data["distributions"],
            "entries": entries,
        }
        atomic(snapshot, native_bytes)
        atomic(companion, json.dumps(result, indent=2, sort_keys=True) + "\n")
