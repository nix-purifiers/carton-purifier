# SPDX-License-Identifier: MIT
import json
import os

VARIABLES = [
    "PERL5LIB",
    "PERL5OPT",
    "PERL_LOCAL_LIB_ROOT",
    "PERL_MB_OPT",
    "PERL_MM_OPT",
    "PERL_CARTON_PATH",
    "PERL_CARTON_CPANFILE",
    "PERL_CPANM_HOME",
    "PERL_CPANM_OPT",
]


def clean_env():
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("CARTON_PURIFIER_")
    }
    for key, value in json.loads(
        os.environ.get("CARTON_PURIFIER_BASE_ENV", "{}")
    ).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def activate(root, environment, companion, snapshot, wrapper_bin):
    env = dict(os.environ)
    original = {key: os.environ.get(key) for key in VARIABLES}
    for key in VARIABLES:
        env.pop(key, None)
    directory = root / ".carton-purifier/sessions" / environment.name
    directory.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "CARTON_PURIFIER_BASE_ENV": os.environ.get(
                "CARTON_PURIFIER_BASE_ENV", json.dumps(original)
            ),
            "CARTON_PURIFIER_PROJECT": str(root),
            "CARTON_PURIFIER_LOCK_FILE": str(companion),
            "CARTON_PURIFIER_SNAPSHOT_FILE": str(snapshot),
            "CARTON_PURIFIER_SNAPSHOT": str(environment / "cpanfile.snapshot"),
            "CARTON_PURIFIER_VENDOR_CACHE": str(root / "vendor/cache"),
            "CARTON_PURIFIER_FROZEN": "1",
            "PERL5LIB": str(environment / "local/lib/perl5"),
            "PERL_CARTON_PATH": str(environment / "local"),
            "PERL_CARTON_CPANFILE": str(root / "cpanfile"),
            "PERL_CPANM_HOME": str(directory / "cpanm"),
        }
    )
    env["PATH"] = (
        str(environment / "local/bin")
        + os.pathsep
        + wrapper_bin
        + os.pathsep
        + env["PATH"]
    )
    return env
