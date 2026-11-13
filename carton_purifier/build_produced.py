# SPDX-License-Identifier: MIT
"""Replay a captured native Carton install against its original Nix suppliers."""
import base64
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from .common import run
from .perl_library import canonical, digest, read_json
from .produced_install import environment, check_collisions


def build(spec_path, output_path):
    spec = read_json(spec_path)
    data = read_json(spec['manifest'])
    profile_path = Path(spec['profile'])
    profile = read_json(profile_path / 'profile.json')
    if data['toolVersions'] != profile['toolVersions'] or data['nativeContext']['profileIdentity'] != profile['profileIdentity']:
        raise ValueError('native produced SDK changed; recapture the lock')
    if canonical(data['provided']) != canonical(profile['provided']):
        raise ValueError('original Nix supplier catalogs changed; recapture the lock')
    if canonical(data['nativeContext']['applicationSdk']) != canonical(profile['applicationSdk']):
        raise ValueError('original selected application SDK changed')
    output = Path(output_path)
    output.mkdir()
    scratch = Path(os.environ['TMPDIR'])
    project = scratch / 'project'
    project.mkdir()
    for name, record in data['inputs'].items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = record['content'].encode()
        if digest(raw) != record['sha256']:
            raise ValueError('authored input bytes differ from capture')
        path.write_bytes(raw)
    shutil.copyfile(spec['snapshot'], project / 'cpanfile.snapshot')
    for entry in data['entries']:
        source = Path(spec['sources']) / entry['path']
        actual = 'sha256-' + base64.b64encode(bytes.fromhex(digest(source.read_bytes()))).decode()
        if actual != entry['hash']:
            raise ValueError('captured native CPAN archive bytes differ')
        target = output / 'vendor/cache' / entry['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source)
    root_identity = scratch / 'root-input.json'
    root_identity.write_bytes(canonical({'input': spec['rootIdentity'], 'sha256': data['inputs']['cpanfile']['sha256']}) + b'\n')
    binding = output / 'root-binding.json'
    effective = output / 'effective.cpanfile'
    invocations = output / 'native-invocations.jsonl'
    env = environment(scratch, project, output / 'local', 'file://' + str(output / 'vendor/cache'),
                      root_identity, binding, effective, invocations)
    command = [profile_path / 'bin/carton', 'install', '--deployment', '--cached']
    command.extend('--without=' + name for name in data['nativeContext']['without'])
    run(command, cwd=project, env=env)
    run([profile_path / 'bin/carton', 'check'], cwd=project, env=env)
    import json
    installed = json.loads(run([profile_path / 'bin/metadata', project / 'cpanfile.snapshot', output / 'local', project / 'cpanfile'],
                               cwd=project, env=env, stdout=subprocess.PIPE, text=True).stdout)
    check_collisions(profile, output / 'local', installed['distributions'])
    if canonical(installed['distributions']) != canonical(data['distributions']):
        raise ValueError('native installed CPAN graph differs from capture')
    actual_binding = read_json(binding)
    captured = data['nativeContext']
    for key in ['originalModel', 'effectiveModel', 'bindings']:
        if canonical(actual_binding[key]) != canonical(captured[key]):
            raise ValueError('native root binding differs from capture: ' + key)
    if digest(effective.read_bytes()) != captured['effectiveCpanfileSha256']:
        raise ValueError('native effective CPANfile differs from capture')
    actual_invocations = [json.loads(line) for line in invocations.read_text().splitlines()]
    if canonical(actual_invocations) != canonical(captured['nativeInvocations']):
        raise ValueError('native phase/feature invocation graph differs from capture')
    if digest((project / 'cpanfile.snapshot').read_bytes()) != data['snapshot']['sha256']:
        raise ValueError('native deployment changed captured snapshot')
    for name in data['inputs']:
        target = output / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / name, target)
    shutil.copyfile(spec['snapshot'], output / 'cpanfile.snapshot')
    shutil.copyfile(spec['snapshot'], output / 'source/cpanfile.snapshot')
    shutil.copyfile(spec['manifest'], output / 'capture.json')
    run([sys.executable, Path(__file__).with_name('normalize.py'), output])
    programs = output / 'bin'
    programs.mkdir()
    shared = ('#!' + spec['runtimeShell'] + '\n'
              'unset PERLLIB PERL5OPT CARTON_PURIFIER_NATIVE_CONTEXT CARTON_PURIFIER_EFFECTIVE_CPANFILE CARTON_PURIFIER_ROOT_IDENTITY\n'
              'export PERL_CARTON_PATH=' + shlex.quote(str(output / 'local')) + '\n'
              'export PERL_CARTON_CPANFILE=' + shlex.quote(str(output / 'source/cpanfile')) + '\n'
              'export CARTON_PURIFIER_ROOT_BINDING=' + shlex.quote(str(binding)) + '\n')
    for tool in ['carton', 'perl']:
        body = shared
        if tool == 'carton':
            body += ('if [ "${1-}" = install ]; then\n shift\n for option in "$@"; do\n'
                     ' case "$option" in --deployment|--cached) ;; *) echo "locked install options are managed by carton-purifier" >&2; exit 1 ;; esac\n done\n'
                     ' exec ' + shlex.quote(str(profile_path / 'bin/carton')) + ' check\nfi\n')
        else:
            body += 'export PERL5LIB=' + shlex.quote(':'.join([str(output / 'local/lib/perl5'), *profile['libraryRoots'], *profile['sdkInc']])) + '\n'
        body += 'exec ' + shlex.quote(str(profile_path / 'bin' / tool)) + ' "$@"\n'
        (programs / tool).write_text(body)
        (programs / tool).chmod(0o555)


if __name__ == '__main__':
    build(*sys.argv[1:])
