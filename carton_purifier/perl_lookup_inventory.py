# SPDX-License-Identifier: MIT
"""Original input owners of all files in the selected Perl lookup trees."""
from pathlib import Path

from perl_library import canonical, digest, within


def inventory(roots, inputs):
    owners = [(Path(row['path']).resolve(strict=True), row['identity']) for row in inputs]
    result = {}

    def visit(path, root, ancestors):
        actual = within(path, [owner for owner, _ in owners])
        if path.is_dir():
            if actual in ancestors:
                raise ValueError('carton-purifier: cycle in native SDK lookup tree')
            for child in sorted(path.iterdir()):
                visit(child, root, ancestors | {actual})
        elif path.is_file():
            matches = [identity for owner, identity in owners if actual.is_relative_to(owner)]
            if len(matches) != 1:
                raise ValueError('carton-purifier: native lookup has no unique original input')
            lookup = path.relative_to(root).as_posix()
            # MakeMaker appends this installation ledger for each independent
            # local installation; it is not a module or native loader input.
            if path.name == 'perllocal.pod':
                return
            row = {'lookup': lookup, 'file': str(actual), 'sha256': digest(actual.read_bytes()), 'input': matches[0]}
            previous = result.setdefault(lookup, row)
            if canonical(previous) != canonical(row):
                raise ValueError('carton-purifier: ambiguous native SDK lookup: ' + lookup)

    for name in roots:
        root = Path(name)
        if root.is_dir():
            visit(root, root, set())
    return [result[name] for name in sorted(result)]
