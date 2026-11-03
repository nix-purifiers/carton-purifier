#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Install the generated source artifact with unmodified native cpanm."""

import json
import os
from pathlib import Path
import subprocess
import sys

repo, root, artifact, temporary = map(lambda value: Path(value).resolve(), sys.argv[1:])


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, text=True, **kwargs)


sdk, cpanm = temporary / "sdk", temporary / "cpanm"
run(["nix", "build", str(repo) + "#sdk", "--out-link", sdk])
expression = f"let f=builtins.getFlake {json.dumps(str(repo))}; pkgs=import f.inputs.nixpkgs {{}}; in pkgs.perlPackages.Appcpanminus"
run(["nix", "build", "--impure", "--expr", expression, "--out-link", cpanm])
env = {
    key: value
    for key, value in os.environ.items()
    if not key.startswith(("CARTON_PURIFIER_", "PERL", "NIX_CFLAGS", "NIX_LDFLAGS"))
    and key
    not in {"CFLAGS", "CPPFLAGS", "CXXFLAGS", "LDFLAGS", "CPATH", "LIBRARY_PATH"}
}
env.update(
    {
        "PATH": str(sdk / "bin") + os.pathsep + env["PATH"],
        "HOME": str(temporary / "consumer-home"),
        "PERL_CPANM_HOME": str(temporary / "consumer-cpanm"),
    }
)
Path(env["HOME"]).mkdir()
consumer = temporary / "consumer"
run(
    [
        cpanm / "bin/cpanm",
        "--notest",
        "-L",
        consumer,
        "--mirror",
        "file://" + str(root / "vendor/cache"),
        "--mirror-only",
        artifact,
    ],
    env=env,
)
probe = 'use JSON::MaybeXS; use Purifier::Example; die "wrong backend" unless JSON::MaybeXS::JSON() eq "Cpanel::JSON::XS"; print Purifier::Example::serialized(),"\\n",$INC{"JSON/MaybeXS.pm"},"\\n";'
result = run(
    [sdk / "bin/perl", "-I" + str(consumer / "lib/perl5"), "-e", probe],
    env=env,
    stdout=subprocess.PIPE,
)
lines = result.stdout.splitlines()
assert json.loads(lines[0]) == {"answer": 42}, result.stdout
assert Path(lines[1]).is_relative_to(consumer), result.stdout
print("Native cpanm consumed source artifact:", artifact)
