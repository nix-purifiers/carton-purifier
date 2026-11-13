# SPDX-License-Identifier: MIT
"""Shared native install context for capture and frozen replay."""
import os
import json
from pathlib import Path
import subprocess


def environment(scratch, project, local, mirror, root_identity, binding, effective, invocations):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('CARTON_PURIFIER_', 'PERL', 'NIX_CFLAGS', 'NIX_LDFLAGS'))
           and key not in {'CC', 'CXX', 'LD', 'AS', 'AR', 'RANLIB', 'CFLAGS', 'CPPFLAGS',
                           'CXXFLAGS', 'LDFLAGS', 'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH',
                           'LIBRARY_PATH', 'PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR'}}
    env.update(HOME=str(scratch / 'home'), PERL_CPANM_HOME=str(scratch / 'cpanm'),
               PERL_CARTON_PATH=str(local), PERL_CARTON_CPANFILE=str(project / 'cpanfile'),
               PERL_CARTON_MIRROR=mirror, CARTON_PURIFIER_NATIVE_CONTEXT=str(invocations),
               CARTON_PURIFIER_ROOT_BINDING=str(binding), CARTON_PURIFIER_EFFECTIVE_CPANFILE=str(effective),
               CARTON_PURIFIER_ROOT_IDENTITY=str(root_identity))
    Path(env['HOME']).mkdir(exist_ok=True)
    return env


def check_collisions(profile, local, distributions):
    for distribution in distributions:
        for package in distribution['provides']:
            if package in profile['providers']:
                raise ValueError('native CPAN package collides with original SDK/producer: ' + package)
    installation = Path(local).resolve(strict=True)
    library = (installation / 'lib/perl5').absolute()
    if not library.resolve(strict=True).is_relative_to(installation):
        raise ValueError('native CPAN library escapes its installation: ' + str(library))
    env = {key: value for key, value in os.environ.items() if not key.startswith('PERL')}
    result = subprocess.run([profile['applicationPerl']['executable'], '-Mlib', '-MJSON::PP', '-e',
                             'lib->import($ARGV[0]); print JSON::PP->new->encode(\\@INC);', str(library)],
                            env=env, text=True, capture_output=True, check=True)
    search_paths = json.loads(result.stdout)
    protected = {row['lookup'] for row in profile['moduleLookups'] + profile['nativeLookups']}
    def walk(path, root, ancestors):
        actual = path.resolve(strict=True)
        if not actual.is_relative_to(installation):
            raise ValueError('native CPAN lookup escapes its installation: ' + str(path))
        if path.is_dir():
            if actual in ancestors:
                raise ValueError('cycle in native CPAN lookup tree: ' + str(path))
            for child in sorted(path.iterdir()):
                walk(child, root, ancestors | {actual})
        elif path.is_file() and path.name != 'perllocal.pod':
            lookup = path.relative_to(root).as_posix()
            if lookup in protected:
                raise ValueError('native CPAN lookup collides with original SDK/producer: ' + lookup)

    # Use the selected interpreter's actual @INC expansion, including its
    # architecture/version directories, rather than inventing a layout matrix.
    for name in search_paths:
        root = Path(name)
        if root.is_dir() and root.absolute().is_relative_to(library):
            # Preserve lexical lookup names while following directory aliases,
            # just as Perl does. Canonical paths establish containment/cycles.
            walk(root, root, set())
