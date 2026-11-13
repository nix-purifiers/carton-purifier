#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Use the installed public CLI and Nix builder with a real native producer."""
import json
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]


def run(args, **options):
    result = subprocess.run(list(map(str, args)), text=True, capture_output=True, **options)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


source = run(['nix', 'eval', '--impure', '--raw', '--expr',
              '(builtins.getFlake ' + json.dumps(str(REPO)) + ').outPath']).strip()
cli = Path(run(['nix', 'build', '--no-link', '--print-out-paths', str(REPO) + '#cli']).strip()) / 'bin/carton-purifier'
with tempfile.TemporaryDirectory(prefix='carton-produced-consumer-') as temporary:
    root = Path(temporary)
    supplier = root / 'supplier'
    supplier.mkdir()
    (supplier / 'flake.nix').write_text('''{ outputs = {self}: let
      f=builtins.getFlake "path:SOURCE";
      pkgs=import f.inputs.nixpkgs {system=builtins.currentSystem;};
      purifier=import(f.inputs.purifier+"/nix/lib"){inherit(pkgs)lib;};
      in {packages.${builtins.currentSystem}.default=import (f.outPath+"/tests/produced-library.nix") {inherit pkgs purifier;};};}
    '''.replace('SOURCE', source))
    original = b"requires 'Owned::Projection', '0.01';\nrequires 'Owned::Projection::Unversioned';\n"
    (root / 'cpanfile').write_bytes(original)
    run([cli, '--project', root, 'lock', '--dependency', './supplier', '--dependency', './supplier'])
    assert (root / 'cpanfile').read_bytes() == original
    lock = json.loads((root / 'carton-purifier.lock.json').read_text())
    assert lock['schemaVersion'] == 2 and lock['entries'] == [] and lock['distributions'] == []
    assert json.loads((root / '.carton-purifier-dependencies.json').read_text()) == ['./supplier']
    environment = Path(run([cli, '--project', root, 'prefetch']).strip())
    assert run([cli, '--project', root, '--native', '--tool=perl', '--', '-MOwned::Projection', '-e',
                'print Owned::Projection::answer(),q(:),Owned::Projection::Unversioned::answer()']) == '42:43'
    assert run([cli, '--project', root, 'shell', '--', 'perl', '-MOwned::Projection', '-e',
                'print Owned::Projection::answer()']) == '42'
    release = Path(run([cli, '--project', root, 'release']).strip())
    assert (release / 'source.tar.gz').is_file()
    saved = {root / name: (root / name).read_bytes() for name in
             ['cpanfile', 'cpanfile.snapshot', 'carton-purifier.lock.json', '.carton-purifier-dependencies.json']}
    missing = subprocess.run([str(cli), '--project', str(root), 'lock', '--dependency', './missing'], text=True, capture_output=True)
    assert missing.returncode != 0
    assert all(path.read_bytes() == content for path, content in saved.items())
    print('actual native producer, unversioned class, CLI lock/replay/shell/release, and rollback PASS')
