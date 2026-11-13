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
    library = (Path(local) / 'lib/perl5').resolve(strict=True)
    env = {key: value for key, value in os.environ.items() if not key.startswith('PERL')}
    result = subprocess.run([profile['applicationPerl']['executable'], '-Mlib', '-MJSON::PP', '-e',
                             'lib->import($ARGV[0]); print JSON::PP->new->encode(\\@INC);', str(library)],
                            env=env, text=True, capture_output=True, check=True)
    search_paths = json.loads(result.stdout)
    protected = {row['lookup'] for row in profile['moduleLookups']}
    # Use the selected interpreter's actual @INC expansion, including its
    # architecture/version directories, rather than inventing a layout matrix.
    for name in search_paths:
        root = Path(name)
        if root.is_dir() and root.resolve(strict=True).is_relative_to(library):
            for file in root.rglob('*.pm'):
                lookup = file.relative_to(root).as_posix()
                if lookup in protected:
                    raise ValueError('native CPAN lookup collides with original SDK/producer: ' + lookup)
