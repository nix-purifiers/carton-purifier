# SPDX-License-Identifier: MIT
"""Inspect actual SDK lookup paths without substituting the capture interpreter."""
from pathlib import Path

from perl_library import canonical, digest, inspect, within


def inventory(request):
    native = inspect(dict(request, xsProbeModules=[]), [], [])
    inputs = [(Path(item['path']).resolve(strict=True), item['identity'])
              for item in request['runtimeInputPaths']]
    allowed = [path for path, _ in inputs]
    lookups = {}

    def visit(path, search_root, ancestors):
        actual = within(path, allowed)
        if path.is_dir():
            if actual in ancestors:
                raise ValueError('carton-purifier: cycle in selected SDK lookup paths')
            for child in sorted(path.iterdir()):
                visit(child, search_root, ancestors | {actual})
        elif path.is_file() and path.name.endswith('.pm'):
            lookup = path.relative_to(search_root).as_posix()
            owners = [identity for root, identity in inputs if actual.is_relative_to(root)]
            if len(owners) != 1:
                raise ValueError('carton-purifier: SDK module has no unique original input owner')
            item = {'lookup': lookup, 'file': str(actual), 'sha256': digest(actual.read_bytes()),
                    'input': owners[0]}
            old = lookups.get(lookup)
            if old is not None and canonical(old) != canonical(item):
                raise ValueError('carton-purifier: ambiguous selected SDK module lookup: ' + lookup)
            lookups[lookup] = item

    for entry in native['inc']:
        root = Path(entry)
        if root.is_dir():
            visit(root, root, set())
    # Metadata comes from the application SDK. It preserves null package
    # versions and does not derive class loader filenames from package names.
    files = [{'root': 'sdk', 'path': key, 'file': row['file']} for key, row in sorted(lookups.items())]
    parsed = inspect(dict(request, xsProbeModules=[]), files, [])
    rows = []
    packages = {}
    for entry in parsed['moduleFiles']:
        row = dict(lookups[entry['path']], packages=entry['packages'])
        rows.append(row)
        for package in row['packages']:
            owners = packages.setdefault(package['name'], {})
            key = canonical(row['input'])
            owners.setdefault(key, []).append({'lookup': row['lookup'], 'file': row['file'],
                                              'version': package['version']})
    # A package can legitimately be split across files in the same SDK input
    # (for example Carp.pm and Carp/Heavy.pm). Distinct input owners remain
    # ambiguous; no distribution VERSION fills an unversioned package field.
    for name, owners in packages.items():
        if len(owners) != 1:
            raise ValueError('carton-purifier: ambiguous SDK package owners: ' + name)
    return {'baseExecutable': parsed['baseExecutable'], 'config': parsed['config'],
            'inc': parsed['inc'], 'modules': rows}
