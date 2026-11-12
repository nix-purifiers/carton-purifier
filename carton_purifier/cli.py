# SPDX-License-Identifier: MIT
"""Native Carton workflows over locked Nix-resolved CPAN distributions."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .capture import capture, relative
from .common import digest, run
from .session import activate, clean_env

PREFIX = "CARTON_PURIFIER_"


def discover(start):
    candidates = [start, *start.parents]
    for name in ["carton-purifier.lock.json", "cpanfile"]:
        for path in candidates:
            if (path / name).exists():
                return path
    return start


def validate(root, companion, snapshot):
    data = json.loads(companion.read_text())
    if data.get("schemaVersion") != 1 or data.get("purifier") != "carton":
        raise ValueError("unsupported lock format; run carton-purifier lock")
    if digest(snapshot.read_bytes()) != data["snapshot"]["sha256"]:
        raise ValueError("native snapshot changed; run carton-purifier lock")
    if data["toolVersions"]["sdk"] != os.environ[PREFIX + "SDK_VERSION"]:
        raise ValueError("Carton SDK changed; run carton-purifier lock")
    for name, record in data["inputs"].items():
        path = root / relative(name)
        if not path.resolve().is_relative_to(root):
            raise ValueError("inputs must stay within the project")
        if digest(path.read_bytes()) != record["sha256"]:
            raise ValueError("Carton inputs changed; run carton-purifier lock")
    return data


def realize(root, companion, snapshot, target="environment"):
    result = run(
        [
            "nix",
            "build",
            "--impure",
            "--file",
            Path(__file__).resolve().parents[1] / "pkgs/build-carton-project/realize.nix",
            "--no-link",
            "--print-out-paths",
            "--argstr",
            "project",
            root,
            "--argstr",
            "companion",
            companion,
            "--argstr",
            "snapshot",
            snapshot,
            "--argstr",
            "target",
            target,
        ],
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    path = Path(result)
    if len(result.splitlines()) != 1 or not path.is_dir():
        raise ValueError("Nix did not return a single output")
    roots = root / ".carton-purifier/gcroots"
    roots.mkdir(parents=True, exist_ok=True)
    for output in [path, Path(os.environ[PREFIX + "SDK"])]:
        run(
            [
                "nix-store",
                "--add-root",
                roots / output.name,
                "--indirect",
                "--realise",
                output,
            ],
            stdout=subprocess.DEVNULL,
        )
    return path


def activated(root, companion, snapshot):
    validate(root, companion, snapshot)
    environment = realize(root, companion, snapshot)
    return activate(
        root, environment, companion, snapshot, os.environ[PREFIX + "WRAPPER_BIN"]
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project")
    parser.add_argument("--lock-file")
    parser.add_argument("--snapshot-file")
    parser.add_argument("--native", action="store_true")
    parser.add_argument(
        "--tool", choices=["carton", "perl", "prove", "perlnavigator"], default="carton"
    )
    parser.add_argument("args", nargs=argparse.REMAINDER)
    opts = parser.parse_args()
    args = opts.args[1:] if opts.args[:1] == ["--"] else opts.args
    root = Path(
        opts.project or os.environ.get(PREFIX + "PROJECT") or discover(Path.cwd())
    ).resolve()
    companion = Path(
        opts.lock_file
        or os.environ.get(PREFIX + "LOCK_FILE")
        or root / "carton-purifier.lock.json"
    ).resolve()
    snapshot = Path(
        opts.snapshot_file
        or os.environ.get(PREFIX + "SNAPSHOT_FILE")
        or root / "cpanfile.snapshot"
    ).resolve()
    native = os.environ[PREFIX + opts.tool.upper()]
    if opts.native:
        if not companion.exists():
            print(
                "carton-purifier: no lockfile; using ordinary impure "
                + opts.tool
                + " resolution",
                file=sys.stderr,
            )
            os.execve(native, [opts.tool, *args], clean_env())
        if (not args and opts.tool == "carton") or args[:1] in (
            ["--help"],
            ["--version"],
            ["-V"],
        ):
            os.execve(native, [opts.tool, *args], clean_env())
        if opts.tool == "carton":
            command = args[0]
            if command not in {
                "install",
                "exec",
                "run",
                "check",
                "list",
                "show",
                "tree",
                "bundle",
            }:
                raise ValueError(
                    "use carton-purifier lock --update for dependency changes"
                )
            if command == "install" and any(
                arg not in {"--deployment", "--cached"} for arg in args[1:]
            ):
                raise ValueError(
                    "locked installation paths and dependency groups are managed by carton-purifier"
                )
            if command == "check" and len(args) > 1:
                raise ValueError(
                    "locked cpanfile selection is managed by carton-purifier"
                )
        env = activated(root, companion, snapshot)
        os.execve(native, [opts.tool, *args], env)
    if not args:
        parser.error("choose lock, prefetch, shell, release, or publish")
    command, rest = args[0], args[1:]
    if command == "lock":
        lock_parser = argparse.ArgumentParser()
        lock_parser.add_argument("--input", action="append")
        lock_parser.add_argument("--update", action="store_true")
        lock_opts = lock_parser.parse_args(rest)
        inputs = lock_opts.input
        if inputs is None:
            inputs = (
                list(json.loads(companion.read_text())["inputs"])
                if companion.exists()
                else []
            )
        capture(
            root,
            companion,
            snapshot,
            os.environ[PREFIX + "CARTON"],
            os.environ[PREFIX + "METADATA_PERL"],
            inputs,
            update=lock_opts.update,
        )
    elif command == "prefetch":
        validate(root, companion, snapshot)
        print(realize(root, companion, snapshot))
    elif command == "shell":
        env = activated(root, companion, snapshot)
        os.chdir(root)
        if rest[:1] == ["--"]:
            rest = rest[1:]
        executable = rest[0] if rest else os.environ.get("SHELL", "sh")
        os.execvpe(executable, rest or [executable], env)
    elif command in {"release", "publish"}:
        validate(root, companion, snapshot)
        release = realize(root, companion, snapshot, "release")
        if command == "release":
            print(release)
            return
        publish = argparse.ArgumentParser()
        publish.add_argument("--repo", required=True)
        publish.add_argument("--tag", required=True)
        options = publish.parse_args(rest)
        artifact = release / "source.tar.gz"
        gh = os.environ.get(PREFIX + "GH", "gh")
        exists = (
            subprocess.run(
                [gh, "release", "view", options.tag, "--repo", options.repo],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        run(
            [
                gh,
                "release",
                "upload",
                options.tag,
                artifact,
                "--repo",
                options.repo,
                "--clobber",
            ]
            if exists
            else [
                gh,
                "release",
                "create",
                options.tag,
                artifact,
                "--repo",
                options.repo,
                "--title",
                options.tag,
                "--notes",
                "Locked Perl project source release",
            ]
        )
    else:
        raise ValueError("unknown command: " + command)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print("carton-purifier: " + str(error), file=sys.stderr)
        sys.exit(1)
