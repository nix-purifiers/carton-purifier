# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import sys

expected, actual = map(lambda name: json.loads(Path(name).read_text()), sys.argv[1:])
if expected["distributions"] != actual["distributions"]:
    raise ValueError(
        "native installed CPAN graph differs from capture; capture a lock for this SDK/platform"
    )
