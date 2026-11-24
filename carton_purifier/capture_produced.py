# SPDX-License-Identifier: MIT
"""Capture a native Carton graph with already verified original Nix suppliers."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .common import atomic, digest, run
from .capture import relative
from .perl_library import canonical, read_json
from .produced_install import environment, check_collisions


def capture_produced(root, companion, snapshot, profile, identity_nix, input_names,
                     without=(), update=False, mirror='https://cpan.metacpan.org'):
    root, profile = Path(root).resolve(), Path(profile).resolve()
    verified = read_json(profile / 'profile.json')
    if verified['format'] != 'carton-produced-profile-v1':
        raise ValueError('unsupported native produced profile')
    # A produced lock always resolves a fresh root install, including --update.
    # This also removes obsolete CPAN entries now supplied by Nix dependencies.
    names = sorted(set(['cpanfile', *input_names]))
    groups = sorted(set(without))
    if any(not isinstance(name, str) or not name or any(char in name for char in '\0\r\n') for name in groups):
        raise ValueError('unsupported native Carton group name')
    records = {}
    with tempfile.TemporaryDirectory(prefix='carton-produced-lock-') as temporary:
        scratch = Path(temporary)
        project = scratch / 'project'
        project.mkdir()
        for name in names:
            path = relative(name)
            if str(path) != name:
                raise ValueError('authored input paths must be canonical')
            source = root / path
            if not source.resolve(strict=True).is_relative_to(root):
                raise ValueError('authored input escapes project')
            content = source.read_bytes()
            target = project / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            records[name] = {'content': content.decode(), 'sha256': digest(content)}
        authored = scratch / 'authored-inputs.json'
        authored.write_bytes(canonical(records) + b'\n')
        identity_env = dict(os.environ, CARTON_PURIFIER_AUTHORED_MANIFEST=str(authored))
        identity = json.loads(run(['nix', 'eval', '--offline', '--impure', '--json', '--file', identity_nix,
                                   '--apply', 'f: f { manifest = builtins.getEnv "CARTON_PURIFIER_AUTHORED_MANIFEST"; }'],
                                  env=identity_env, stdout=subprocess.PIPE, text=True).stdout)
        # This is an actual Nix-created immutable source manifest containing
        # the complete authored bytes, not a fabricated derivation identity.
        if Path(identity['path']).read_bytes() != authored.read_bytes():
            raise ValueError('Nix authored input manifest differs')
        root_identity = scratch / 'root-input.json'
        root_identity.write_bytes(canonical({'input': identity['input'], 'sha256': records['cpanfile']['sha256']}) + b'\n')
        effective = scratch / 'effective.cpanfile'
        binding_path = scratch / 'root-binding.json'
        invocations_path = scratch / 'native-invocations.jsonl'
        env = environment(scratch, project, project / 'local', mirror, root_identity,
                          binding_path, effective, invocations_path)
        command = [profile / 'bin/carton', 'install']
        for group in groups:
            command.append('--without=' + group)
        # A schema2 lock is always captured from a fresh native installation;
        # an existing snapshot must not retain an obsolete provided CPAN dist.
        run(command, cwd=project, env=env)
        run([profile / 'bin/carton', 'check'], cwd=project, env=env)
        native_snapshot = (project / 'cpanfile.snapshot').read_bytes()
        data = json.loads(run([profile / 'bin/metadata', project / 'cpanfile.snapshot',
                               project / 'local', project / 'cpanfile'], cwd=project, env=env,
                              stdout=subprocess.PIPE, text=True).stdout)
        if data['formatVersion'] != '1.0':
            raise ValueError('unsupported native Carton snapshot format')
        check_collisions(verified, project / 'local', data['distributions'])
        entries = []
        for distribution in data['distributions']:
            pathname = distribution['pathname']
            if not re.fullmatch(r'[A-Za-z0-9]/[A-Za-z0-9]{2}/[A-Za-z0-9_-]+/[A-Za-z0-9_.+-]+', pathname):
                raise ValueError('unsupported native CPAN archive path')
            archive = project / 'local/cache/authors/id' / pathname
            raw = archive.read_bytes()
            entries.append({'path': 'authors/id/' + pathname,
                            'url': 'https://cpan.metacpan.org/authors/id/' + pathname,
                            'hash': 'sha256-' + base64.b64encode(bytes.fromhex(digest(raw))).decode(),
                            'mirrors': ['https://backpan.perl.org/authors/id/' + pathname]})
        binding = read_json(binding_path)
        invocations = [json.loads(line) for line in invocations_path.read_text().splitlines()]
        context = {'format': 'carton-produced-context-v1', 'profileIdentity': verified['profileIdentity'],
                   'applicationSdk': verified['applicationSdk'], 'without': groups,
                   **{key: binding[key] for key in ['originalModel', 'effectiveModel', 'bindings']},
                   'effectiveCpanfile': effective.read_text(), 'effectiveCpanfileSha256': digest(effective.read_bytes()),
                   'providedGraphIdentity': digest(canonical(verified['provided'])),
                   'nativeSnapshotSha256': digest(native_snapshot),
                   'nativeInstalledGraphSha256': digest(canonical(data['distributions'])),
                   'nativeInvocations': invocations}
        result = {'schemaVersion': 2, 'purifier': 'carton', 'inputs': records,
                  'snapshot': {'sha256': digest(native_snapshot)}, 'distributions': data['distributions'],
                  'entries': entries, 'toolVersions': verified['toolVersions'],
                  'provided': verified['provided'], 'nativeContext': context}
        atomic(snapshot, native_snapshot)
        atomic(companion, json.dumps(result, sort_keys=True, indent=2) + '\n')
        return result
