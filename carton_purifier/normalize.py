# SPDX-License-Identifier: MIT
from pathlib import Path
import json
import re
import sys

root = Path(sys.argv[1])
lib_root = Path(sys.argv[2]) if len(sys.argv) > 2 else root / "local/lib/perl5"
for path in lib_root.glob("*/.meta/*/install.json"):
    data = json.loads(path.read_text())
    path.chmod(path.stat().st_mode | 0o200)
    path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
index = root / "local/cache/modules/02packages.details.txt"
if index.exists():
    text, count = re.subn(
        r"^Last-Updated:.*$",
        "Last-Updated: Thu Jan  1 00:00:01 1970",
        index.read_text(),
        flags=re.M,
    )
    assert count == 1
    index.write_text(text)
for path in lib_root.glob("*/perllocal.pod"):
    parts = path.read_text().split("=head2 ")
    path.chmod(path.stat().st_mode | 0o200)
    path.write_text(parts[0] + "".join("=head2 " + part for part in sorted(parts[1:])))
