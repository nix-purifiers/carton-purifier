# SPDX-License-Identifier: MIT
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlsplit


def run(args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def valid_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("sources must use public HTTPS URLs without credentials")
    return url


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    data = data.encode() if isinstance(data, str) else data
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == data:
        return
    fd, filename = tempfile.mkstemp(prefix=".spago-purifier-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(filename, path)
    finally:
        Path(filename).unlink(missing_ok=True)
