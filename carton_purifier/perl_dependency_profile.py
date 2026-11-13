# SPDX-License-Identifier: MIT
"""Add actual Nix suppliers to the owning CLI's immutable SDK declaration."""
import sys
import tempfile
from pathlib import Path

from perl_library import canonical, read_json
from perl_profile import build


def main(request_path, output):
    request = read_json(request_path)
    if set(request) != {'ownerDeclaration', 'suppliers'}:
        raise ValueError('unsupported owning dependency profile request')
    declared = read_json(request['ownerDeclaration'])
    if declared['suppliers']:
        raise ValueError('owning CLI SDK declaration already contains suppliers')
    declared = dict(declared, suppliers=request['suppliers'])
    with tempfile.TemporaryDirectory(prefix='carton-dependency-profile-') as directory:
        merged = Path(directory) / 'request.json'
        merged.write_bytes(canonical(declared) + b'\n')
        build(merged, Path(output) / 'profile.json')


if __name__ == '__main__':
    main(*sys.argv[1:])
