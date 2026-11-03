# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import shutil
import subprocess
import sys

manifest, snapshot, sources, work, output, perl, snapshot_script = map(
    Path, sys.argv[1:]
)
data = json.loads(manifest.read_text())
for name, record in data["inputs"].items():
    path = work / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(record["content"].encode())
shutil.copyfile(snapshot, work / "cpanfile.snapshot")
actual = json.loads(
    subprocess.check_output([perl, snapshot_script, snapshot], text=True)
)
if actual["distributions"] != data["distributions"]:
    raise ValueError(
        "native snapshot metadata differs from captured distribution graph"
    )
for entry in data["entries"]:
    target = output / "vendor/cache" / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(sources / entry["path"])
