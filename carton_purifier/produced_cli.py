# SPDX-License-Identifier: MIT
"""Native CLI projection workflows using the owning, immutable SDK profile."""
import json
import os
from pathlib import Path
import subprocess

from .common import atomic, digest, run
from .capture_produced import capture_produced
from .perl_library import canonical

LOCATORS = '.carton-purifier-dependencies.json'


def references(root):
    value = json.loads((root / LOCATORS).read_text())
    if not isinstance(value, list) or not value or any(not isinstance(x, str) or not x for x in value):
        raise ValueError('Perl dependencies must be a nonempty list of Nix installables')
    if value != sorted(set(value)):
        raise ValueError('Perl dependency locators must be sorted and unique')
    result = []
    for reference in value:
        source, marker, attribute = reference.partition('#')
        if source.startswith(('.', '/')):
            source = 'path:' + str((root / source).resolve())
        elif source.startswith('path:'):
            path, query, options = source[5:].partition('?')
            source = 'path:' + str((root / path).resolve()) + query + options
        result.append(source + marker + attribute)
    return result


def command(root, companion, snapshot, target):
    return ['nix', 'build', '--impure', '--no-link', '--print-out-paths', '--file',
            Path(__file__).resolve().parents[1] / 'pkgs/build-carton-project/realize-produced.nix',
            '--argstr', 'project', root, '--argstr', 'companion', companion,
            '--argstr', 'snapshot', snapshot, '--argstr', 'target', target,
            '--argstr', 'references', json.dumps(references(root))]


def profile(root, companion, snapshot):
    result = run(command(root, companion, snapshot, 'profile'), stdout=subprocess.PIPE, text=True).stdout.strip()
    if len(result.splitlines()) != 1 or not Path(result).is_dir():
        raise ValueError('Nix did not return one owning Perl profile')
    return Path(result)


def validate(root, companion, snapshot, data):
    if data.get('schemaVersion') != 2 or data.get('purifier') != 'carton':
        raise ValueError('unsupported produced Carton lock')
    if LOCATORS not in data['inputs']:
        raise ValueError('Perl dependency locators are missing; recapture with --dependency')
    for name, record in data['inputs'].items():
        from .capture import relative
        source = root / relative(name)
        if not source.resolve(strict=True).is_relative_to(root):
            raise ValueError('Carton inputs escape project')
        if source.read_bytes() != record['content'].encode() or digest(source.read_bytes()) != record['sha256']:
            raise ValueError('Carton inputs changed; run carton-purifier lock')
    if digest(snapshot.read_bytes()) != data['snapshot']['sha256']:
        raise ValueError('native snapshot changed; run carton-purifier lock')
    actual = json.loads((profile(root, companion, snapshot) / 'profile.json').read_text())
    if (data['toolVersions'] != actual['toolVersions']
            or canonical(data['nativeContext']['applicationSdk']) != canonical(actual['applicationSdk'])
            or canonical(data['provided']) != canonical(actual['provided'])
            or data['nativeContext']['profileIdentity'] != actual['profileIdentity']):
        raise ValueError('original Perl SDK or supplier projections changed; recapture the lock')
    return data


def lock(root, companion, snapshot, inputs, dependencies, without, update):
    saved = {path: path.read_bytes() if path.exists() else None
             for path in [root / LOCATORS, companion, snapshot]}
    try:
        if dependencies is not None:
            if any(not item or any(char in item for char in '\0\r\n') for item in dependencies):
                raise ValueError('invalid Perl dependency locator')
            atomic(root / LOCATORS, canonical(sorted(set(dependencies))) + b'\n')
        selected = profile(root, companion, snapshot)
        if without is None:
            without = json.loads(companion.read_text())['nativeContext']['without'] if companion.exists() and json.loads(companion.read_text()).get('schemaVersion') == 2 else []
        return capture_produced(root, companion, snapshot, selected,
                                Path(__file__).resolve().parents[1] / 'pkgs/build-carton-project/authored-input.nix',
                                sorted(set([*inputs, LOCATORS])), without=without, update=update)
    except BaseException:
        for path, content in saved.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic(path, content)
        raise


def activate(env, environment):
    profile_data = json.loads((environment / 'profile.json').read_text())
    env['PERL5LIB'] = os.pathsep.join([str(environment / 'local/lib/perl5'),
                                     *profile_data['libraryRoots'], *profile_data['sdkInc']])
    env['PATH'] = str(environment / 'bin') + os.pathsep + env['PATH']
    env['CARTON_PURIFIER_PRODUCED_ENVIRONMENT'] = str(environment)
    env['CARTON_PURIFIER_PRODUCED_PERL'] = profile_data['applicationPerl']['executable']
    return env
