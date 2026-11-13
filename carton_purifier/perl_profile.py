# SPDX-License-Identifier: MIT
"""Verify original Perl suppliers before exposing them to native Carton."""
from pathlib import Path
import sys

from perl_library import canonical, digest, read_json
from perl_projector import project, verify_sdk_modules
from perl_sdk_inventory import inventory


def profile(declared):
    sdk = inventory(declared)
    providers, lookups, distributions, roots, originals = {}, {}, [], [], {}
    sdk_packages, package_owners, ambiguous = {}, {}, []

    def claim(table, name, value):
        previous = table.setdefault(name, value)
        if canonical(previous) != canonical(value):
            raise ValueError('carton-purifier: conflicting application library owner: ' + name)

    for row in sdk['modules']:
        claim(lookups, row['lookup'], row['input'])
        for package in row['packages']:
            claim(package_owners, package['name'], row['input'])
            sdk_packages.setdefault(package['name'], []).append((row, package))
    for name, declarations in sdk_packages.items():
        # Preserve the SDK's actual native loader lookup when a package is
        # also declared elsewhere (DB in Carp.pm, DB.pm and sigtrap.pm).
        native_lookup = name.replace('::', '/') + '.pm'
        chosen = [(row, package) for row, package in declarations if row['lookup'] == native_lookup]
        if not chosen:
            versions = {canonical(package['version']) for _, package in declarations}
            if len(versions) != 1:
                ambiguous.append(name)
                continue
            chosen = declarations[:1]
        row, package = chosen[0]
        providers[name] = {'nativeVersion': package['version'], 'providerIdentity': row['input'], 'declaredIn': []}
    # Perl itself is a native interpreter requirement, not a fabricated module.
    providers['perl'] = {'nativeVersion': sdk['config']['version'],
                         'providerIdentity': declared['applicationPerl']['identity'], 'declaredIn': []}
    for supplier in declared['suppliers']:
        catalog, supplied, supplied_roots = project(supplier['declared'], supplier['observation'], supplier['loader'])
        if Path(supplier['catalog']).read_bytes() != canonical(catalog) + b'\n':
            raise ValueError('carton-purifier: stale native profile supplier catalog')
        roots.extend(supplied_roots)
        for producer in supplied:
            key = canonical(producer['identity'])
            if key in originals:
                if canonical(originals[key]) != canonical(producer):
                    raise ValueError('carton-purifier: inconsistent native profile supplier')
                continue
            originals[key] = producer
            native = producer['sdk']
            if native['baseExecutable'] != sdk['baseExecutable'] or canonical(native['config']) != canonical(sdk['config']):
                raise ValueError('carton-purifier: native profile supplier SDK differs')
            verify_sdk_modules(producer['sdkInventory'], sdk)
            for root in producer['roots']:
                for item in root['loadableFiles']:
                    claim(lookups, item['lookup'], producer['identity'])
            provides = {}
            for package in producer['packages']:
                claim(package_owners, package['name'], producer['identity'])
                claim(providers, package['name'], {'nativeVersion': package['version'],
                      'providerIdentity': producer['identity'], 'declaredIn': package['declaredIn']})
                provides[package['name']] = {'version': package['version']}
            # Carton's Tree needs the native runtime edges of each produced
            # distribution. Preserve each set for native constraint merging.
            distributions.append({'identity': digest(key), 'provides': provides,
                                  'requirementSets': producer['runtimeRequirements']})
    return {'format': 'carton-produced-profile-v1', 'providers': providers,
            'distributions': distributions, 'libraryRoots': list(dict.fromkeys(roots)),
            'sdkInc': sdk['inc'], 'sdkInventory': sdk, 'ambiguousSdkPackages': sorted(ambiguous),
            'applicationPerl': declared['applicationPerl']}


if __name__ == '__main__':
    result = profile(read_json(sys.argv[1]))
    Path(sys.argv[2]).write_bytes(canonical(result) + b'\n')
