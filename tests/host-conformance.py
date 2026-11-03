#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, text=True, **kwargs)


case = sys.argv[1]
with tempfile.TemporaryDirectory(prefix="carton-conformance-") as temporary:
    temp = Path(temporary)
    cli = temp / "cli"
    run(["nix", "build", str(REPO) + "#cli", "--out-link", cli])
    helper = cli / "bin/carton-purifier"
    root = temp / "project"
    shutil.copytree(
        REPO / "examples/minimal",
        root,
        ignore=shutil.ignore_patterns(
            ".carton-purifier",
            "local",
            "blib",
            "vendor",
            "Makefile",
            "MYMETA.*",
            "*.log",
        ),
    )
    companion, snapshot = root / "carton-purifier.lock.json", root / "cpanfile.snapshot"
    args = [helper, "--project", root]
    if case == "empty":
        companion.unlink()
        snapshot.unlink()
        (root / "cpanfile").write_text("requires 'perl', '5.006';\n")
        run([*args, "lock"])
        assert json.loads(companion.read_text())["entries"] == []
        run([*args, "prefetch"])
        run([*args, "shell", "--", "carton", "install"])
        probe = run(
            [*args, "shell", "--", "perl", "-e", 'print "empty graph\\n"'],
            stdout=subprocess.PIPE,
        )
        assert probe.stdout == "empty graph\n"
        poison = root / "local/lib/perl5/JSON/MaybeXS.pm"
        poison.parent.mkdir(parents=True, exist_ok=True)
        poison.write_text("package JSON::MaybeXS; 1;\n")
        rejected = subprocess.run(
            [*map(str, args), "shell", "--", "perl", "-MJSON::MaybeXS", "-e", "1"],
            capture_output=True,
            text=True,
        )
        assert (
            rejected.returncode != 0
            and "Can't locate JSON/MaybeXS.pm" in rejected.stderr
        )
        print("Carton conformance passed: empty")
        sys.exit(0)
    if case == "external":
        companion.rename(temp / "external.json")
        snapshot.rename(temp / "external.snapshot")
        companion, snapshot = temp / "external.json", temp / "external.snapshot"
        args += ["--lock-file", companion, "--snapshot-file", snapshot]
    if case == "relock":
        before = companion.read_bytes(), snapshot.read_bytes()
        run([*args, "lock"])
        assert before == (companion.read_bytes(), snapshot.read_bytes())
    if case == "update":
        manifest = root / "cpanfile"
        text = manifest.read_text()
        manifest.write_text(
            text
            + "requires 'Try::Tiny', '== 0.31', dist => 'E/ET/ETHER/Try-Tiny-0.31.tar.gz';\n"
        )
        run([*args, "lock"])
        first = json.loads(companion.read_text())
        assert any(
            d["provides"].get("Try::Tiny", {}).get("version") == "0.31"
            for d in first["distributions"]
        )
        manifest.write_text(text + "requires 'Try::Tiny', '0.31';\n")
        run([*args, "lock", "--update"])
        updated = json.loads(companion.read_text())
        assert any(
            d["provides"].get("Try::Tiny", {}).get("version") != "0.31"
            for d in updated["distributions"]
            if "Try::Tiny" in d["provides"]
        )
    if case == "inputs":
        extra = root / "extra.pl"
        extra.write_text("requires 'Try::Tiny', '0.31'; 1;\n")
        with (root / "cpanfile").open("a") as stream:
            stream.write("do './extra.pl' or die $@ || $!;\n")
        run([*args, "lock", "--input", "extra.pl"])
        assert "extra.pl" in json.loads(companion.read_text())["inputs"]
    environment = Path(run([*args, "prefetch"], stdout=subprocess.PIPE).stdout.strip())
    poison = root / "local/lib/perl5/JSON/MaybeXS.pm"
    poison.parent.mkdir(parents=True, exist_ok=True)
    poison.write_text('die "ordinary cache poison";\n')
    run([*args, "shell", "--", "carton", "install"])
    run([*args, "shell", "--", "carton", "exec", "prove", "-lr", "t"])
    output = run(
        [*args, "shell", "--", "carton", "exec", "perl", "-Ilib", "bin/example"],
        stdout=subprocess.PIPE,
    )
    assert json.loads(output.stdout) == {"answer": 42}
    if case == "native":
        source = root / "lib/Purifier/Example.pm"
        original = source.read_text()
        source.write_text(original.replace("sub answer { 42 }", "sub answer { 43 }"))
        output = run(
            [*args, "shell", "--", "perl", "-Ilib", "bin/example"],
            stdout=subprocess.PIPE,
        )
        assert json.loads(output.stdout) == {"answer": 43}
        failed = subprocess.run(
            [*map(str, args), "shell", "--", "prove", "-lr", "t"],
            capture_output=True,
            text=True,
        )
        assert failed.returncode != 0 and "Failed" in failed.stdout
        source.write_text(original)
        unchanged = Path(
            run([*args, "prefetch"], stdout=subprocess.PIPE).stdout.strip()
        )
        assert environment == unchanged
        flagged = run(
            [
                *args,
                "shell",
                "--",
                "carton",
                "exec",
                "perl",
                "-Ilib",
                "-MPurifier::Example",
                "-e",
                "print Purifier::Example::serialized()",
                "--",
                "--version",
            ],
            stdout=subprocess.PIPE,
        )
        assert json.loads(flagged.stdout) == {"answer": 42}
        run(["python3", REPO / "tests/editor.py", root, helper])
        native, sdk = temp / "native", temp / "sdk"
        run(["nix", "build", str(REPO) + "#native", "--out-link", native])
        run(["nix", "build", str(REPO) + "#sdk", "--out-link", sdk])
        unlocked = temp / "unlocked"
        shutil.copytree(
            root,
            unlocked,
            ignore=shutil.ignore_patterns(
                ".carton-purifier", "local", "vendor", "*.log"
            ),
        )
        (unlocked / "carton-purifier.lock.json").unlink()
        script = (
            'my $input=<STDIN>; print "OUT:$input"; print STDERR "ERR:$input"; exit 7;'
        )
        command = ["exec", sdk / "bin/perl", "-e", script]
        baseline = subprocess.run(
            [native / "bin/carton", *command],
            cwd=unlocked,
            input="probe\n",
            capture_output=True,
            text=True,
        )
        fallback = subprocess.run(
            [cli / "bin/carton", *command],
            cwd=unlocked,
            input="probe\n",
            capture_output=True,
            text=True,
        )
        assert baseline.returncode == fallback.returncode == 7
        assert fallback.stdout == baseline.stdout == "OUT:probe\n"
        warning, rest = fallback.stderr.split("\n", 1)
        assert "no lockfile" in warning and "impure" in warning
        assert rest == baseline.stderr == "ERR:probe\n"
    if case == "bundle":
        run([*args, "shell", "--", "carton", "bundle"])
        data = json.loads(companion.read_text())
        for entry in data["entries"]:
            archive = root / "vendor/cache" / entry["path"]
            assert archive.is_file()
            assert (
                hashlib.sha256(archive.read_bytes()).digest()
                == hashlib.sha256(
                    (environment / "sources" / entry["path"]).read_bytes()
                ).digest()
            )
        assert (root / "vendor/cache/modules/02packages.details.txt.gz").is_file()
    if case == "release":
        release = (
            Path(run([*args, "release"], stdout=subprocess.PIPE).stdout.strip())
            / "source.tar.gz"
        )
        with tarfile.open(release) as archive:
            names = archive.getnames()
            assert (
                "source/cpanfile.snapshot" in names
                and "source/carton-purifier.lock.json" in names
            )
            assert (
                archive.extractfile("source/cpanfile.snapshot").read()
                == snapshot.read_bytes()
            )
            assert not any(
                "/local/" in name or "/.carton-purifier/" in name or "/blib/" in name
                for name in names
            )
        run([*args, "shell", "--", "carton", "bundle"])
        run(["python3", REPO / "tests/consumer.py", REPO, root, release, temp])
        fake = temp / "gh"
        fake.write_text(
            "#!"
            + sys.executable
            + "\n"
            + """
import hashlib,json,os,pathlib,sys
args=sys.argv[1:]
state=pathlib.Path(os.environ['FAKE_GH_STATE'])
if args[:2]==['release','view']:sys.exit(0 if state.exists() else 1)
assert args[:2] in (['release','create'],['release','upload']),args
artifact=pathlib.Path(args[3]);assert artifact.is_file()
with open(os.environ['FAKE_GH_LOG'],'a') as stream:stream.write(json.dumps({'args':args,'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()})+'\\n')
state.write_text('created')
"""
        )
        fake.chmod(0o755)
        env = os.environ | {
            "CARTON_PURIFIER_GH": str(fake),
            "FAKE_GH_STATE": str(temp / "created"),
            "FAKE_GH_LOG": str(temp / "publish.jsonl"),
        }
        for _ in range(2):
            run([*args, "publish", "--repo", "example/project", "--tag", "v1"], env=env)
        records = [
            json.loads(line)
            for line in (temp / "publish.jsonl").read_text().splitlines()
        ]
        assert records[0]["args"][:2] == ["release", "create"] and records[1]["args"][
            :2
        ] == ["release", "upload"]
        assert all(
            record["sha256"] == hashlib.sha256(release.read_bytes()).hexdigest()
            for record in records
        )
    if case == "inputs":
        (root / "extra.pl").write_text("requires 'Try::Tiny', '0.32'; 1;\n")
        refused = subprocess.run(
            [*map(str, args), "prefetch"], capture_output=True, text=True
        )
        assert refused.returncode != 0 and "inputs changed" in refused.stderr
        outside = temp / "outside.pl"
        outside.write_text("1;\n")
        (root / "escaped.pl").symlink_to(outside)
        before = companion.read_bytes(), snapshot.read_bytes()
        refused = subprocess.run(
            [*map(str, args), "lock", "--input", "escaped.pl"],
            capture_output=True,
            text=True,
        )
        assert refused.returncode != 0 and "within the project" in refused.stderr
        assert before == (companion.read_bytes(), snapshot.read_bytes())
    else:
        snapshot.write_text(snapshot.read_text() + "\n")
        refused = subprocess.run(
            [*map(str, args), "prefetch"], capture_output=True, text=True
        )
        assert refused.returncode != 0 and "snapshot changed" in refused.stderr
    print("Carton conformance passed:", case)
