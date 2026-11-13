# SPDX-License-Identifier: MIT
"""Build an installed-library catalog from original constructor declarations."""
import copy
from pathlib import Path
import shlex
import sys

from perl_capture_context import reconstruct
from perl_library import canonical, digest, read_json, verify
from perl_sdk_inventory import inventory


def project(declared, observation_path, loader):
    dependencies = []
    providers = []
    search_roots = []
    seen = set()
    for supplier in declared['suppliers']:
        request = supplier['declared']
        key = canonical(request['producerIdentity'])
        if key in seen:
            raise ValueError('carton-purifier: duplicate library supplier')
        seen.add(key)
        catalog, nested, roots = project(request, supplier['observation'], supplier['loader'])
        raw = Path(supplier['catalog']).read_bytes()
        if raw != canonical(catalog) + b'\n':
            raise ValueError('carton-purifier: stale dependency library catalog')
        dependencies.append({'input': request['producerIdentity'], 'catalogSha256': digest(raw),
                             'semanticIdentity': catalog['semanticIdentity']})
        providers.extend(nested)
        search_roots.extend(roots)

    request, observation = reconstruct(declared, observation_path)
    if canonical(observation['dependencies']) != canonical(dependencies):
        raise ValueError('carton-purifier: production dependency context differs from original suppliers')
    request['dependencies'] = dependencies
    current = verify(request, observation)
    sdk = inventory(request)
    if sdk['baseExecutable'] != current['sdk']['baseExecutable'] or canonical(sdk['config']) != canonical(current['sdk']['config']):
        raise ValueError('carton-purifier: selected SDK changed during library verification')

    own = {'identity': declared['producerIdentity'], 'roots': current['roots'],
           'packages': current['packages'], 'sdk': current['sdk']}
    providers.insert(0, own)
    # Repeated transitive references to the identical original input coalesce;
    # equal package versions or equal bytes under distinct owners never do.
    unique = {}
    for provider in providers:
        key = canonical(provider['identity'])
        if key in unique and canonical(unique[key]) != canonical(provider):
            raise ValueError('carton-purifier: inconsistent repeated library supplier')
        unique[key] = provider
    providers = list(unique.values())
    lookups, packages = {}, {}

    def claim(table, name, owner, label):
        old = table.setdefault(name, owner)
        if old != owner:
            raise ValueError('carton-purifier: ambiguous ' + label + ': ' + name)

    for row in sdk['modules']:
        owner = canonical(row['input'])
        claim(lookups, row['lookup'], owner, 'module lookup')
        for package in row['packages']:
            claim(packages, package['name'], owner, 'package owner')
    for provider in providers:
        if provider['sdk']['baseExecutable'] != current['sdk']['baseExecutable'] or canonical(provider['sdk']['config']) != canonical(current['sdk']['config']):
            raise ValueError('carton-purifier: incompatible supplier Perl SDK')
        # Retain the caller-selected module environment: accepting a supplier
        # whose additional SDK modules are absent would silently lose runtime
        # dependencies when loading with the caller's interpreter.
        if canonical(provider['sdk']['runtimeInputs']) != canonical(current['sdk']['runtimeInputs']):
            raise ValueError('carton-purifier: supplier SDK module environment differs')
        owner = canonical(provider['identity'])
        for root in provider['roots']:
            for row in root['loadableFiles']:
                claim(lookups, row['lookup'], owner, 'module lookup')
        for package in provider['packages']:
            claim(packages, package['name'], owner, 'package owner')

    traces = copy.deepcopy(current['xsLoads'])
    for trace in traces:
        for obj in trace['sharedObjects']:
            tag = obj['input']
            # verify() has just replayed physical ownership, bytes and SDK
            # traces; only now replace the producer's nonrecursive tag.
            obj['input'] = declared['producerIdentity'] if tag == {'kind': 'producer'} else tag['identity']
    catalog = {'format': 'perl', 'profile': 'installed-library-v1',
               'producerIdentity': declared['producerIdentity'],
               'sourceIdentity': declared['sourceIdentity'],
               'projectorIdentity': declared['projectorIdentity'],
               'observationSha256': digest(Path(observation_path).read_bytes()),
               **{key: current[key] for key in ['roots', 'packages', 'nativeMetadata', 'sdk', 'moduleMappings']},
               'dependencies': dependencies, 'xsLoads': traces}
    semantic = {key: value for key, value in catalog.items() if key != 'observationSha256'}
    semantic['producerOutputs'] = declared['producerOutputs']
    catalog['semanticIdentity'] = digest(canonical(semantic))
    catalog['loader'] = loader
    own_roots = [str(Path(declared['producerPath']) / root['path']) for root in current['roots']]
    return catalog, providers, list(dict.fromkeys(own_roots + search_roots))


def build(request_path, output):
    declared = read_json(request_path)
    output = Path(output)
    loader = output / 'bin/perl'
    catalog, _, roots = project(declared, declared['observation'], str(loader))
    loader.parent.mkdir(parents=True)
    # Explicit original roots are arguments to the original application Perl.
    # Ambient Perl switches and PERL5LIB must not insert unobserved providers.
    args = [catalog['sdk']['executable'], *['-I' + root for root in roots]]
    loader.write_text('#!' + declared['runtimeShell'] + '\n'
                      'unset PERL5LIB PERLLIB PERL5OPT\nexec ' + shlex.join(args) + ' "$@"\n')
    loader.chmod(0o555)
    (output / 'catalog.json').write_bytes(canonical(catalog) + b'\n')


if __name__ == '__main__':
    build(*sys.argv[1:])
