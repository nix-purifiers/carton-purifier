# SPDX-License-Identifier: MIT
"""Verify original Perl suppliers before exposing them to native Carton."""
from pathlib import Path
import shlex
import sys

from perl_library import canonical, digest, inspect, read_json, within
from perl_projector import project, verify_sdk_modules
from perl_sdk_inventory import inventory
from perl_lookup_inventory import inventory as lookup_inventory


def profile(declared):
    sdk = inventory(declared)
    native_lookups = lookup_inventory(sdk['inc'], declared['runtimeInputPaths'])
    native = inspect(declared, [], [])
    tool_native = inspect(declared['toolSdk'], [], [])
    if tool_native['baseExecutable'] != sdk['baseExecutable'] or canonical(tool_native['config']) != canonical(sdk['config']):
        raise ValueError('carton-purifier: native framework tooling must retain the selected application Perl base SDK')
    application_sdk = {'applicationPerl': declared['applicationPerl']['identity'],
                       'executable': declared['applicationPerl']['executable'],
                       'baseExecutable': sdk['baseExecutable'], 'config': sdk['config'],
                       'runtimeInputs': declared['runtimeInputs'], 'inc': sdk['inc'], 'moduleOrigins': []}
    for module in native['moduleOrigins']:
        actual = within(module['file'], [Path(row['path']).resolve(strict=True) for row in declared['runtimeInputPaths']])
        owners = [row['identity'] for row in declared['runtimeInputPaths'] if actual.is_relative_to(Path(row['path']).resolve(strict=True))]
        if len(owners) != 1:
            raise ValueError('carton-purifier: selected application SDK module has no unique original owner')
        application_sdk['moduleOrigins'].append(dict(module, input=owners[0]))
    providers, lookups, distributions, roots, originals = {}, {}, [], [], {}
    sdk_packages, package_owners, ambiguous, provided = {}, {}, [], {}

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
    sdk_node = {'identity': declared['applicationPerl']['identity'],
                'baseIdentity': declared['basePerl']['identity'],
                'runtimeInputs': declared['runtimeInputs'],
                'provides': {name: {'version': row['nativeVersion']} for name, row in providers.items()}}
    for supplier in declared['suppliers']:
        catalog, supplied, supplied_roots = project(supplier['declared'], supplier['observation'], supplier['loader'])
        if Path(supplier['catalog']).read_bytes() != canonical(catalog) + b'\n':
            raise ValueError('carton-purifier: stale native profile supplier catalog')
        entry = {'input': catalog['producerIdentity'], 'semanticIdentity': catalog['semanticIdentity'],
                 'catalogSha256': digest(Path(supplier['catalog']).read_bytes())}
        claim(provided, canonical(entry['input']), entry)
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
                for item in root['payload']:
                    if item['type'] in {'file', 'link'}:
                        actual = Path(item['resolvedOrigin'])
                        if actual.is_file():
                            native_lookups.append({'lookup': item['path'], 'file': str(actual),
                                                   'sha256': digest(actual.read_bytes()), 'input': producer['identity']})
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
    profile_identity = digest(canonical({'tools': declared['toolsIdentity'], 'framework': declared['toolSdk'],
                                        'nativeTools': declared['nativeTools'],
                                        'applicationSdk': application_sdk}))
    return {'format': 'carton-produced-profile-v1', 'providers': providers,
            'distributions': distributions, 'libraryRoots': list(dict.fromkeys(roots)),
            'sdkInc': sdk['inc'], 'sdkInventory': sdk, 'ambiguousSdkPackages': sorted(ambiguous),
            'sdkNode': sdk_node,
            'applicationPerl': declared['applicationPerl'], 'applicationSdk': application_sdk,
            'provided': sorted(provided.values(), key=canonical), 'profileIdentity': profile_identity,
            'moduleLookups': [{'lookup': name, 'input': owner} for name, owner in sorted(lookups.items())],
            'nativeLookups': sorted(native_lookups, key=canonical),
            'toolVersions': dict(declared['toolVersions'], sdk=profile_identity)}


def build(request_path, output_path):
    declared = read_json(request_path)
    result = profile(declared)
    output = Path(output_path)
    output.write_bytes(canonical(result) + b'\n')
    programs = output.parent / 'bin'
    programs.mkdir()
    commands = {
        'carton': [declared['toolSdk']['applicationPerl']['executable'], '-I' + declared['toolsPath'],
                   str(Path(declared['toolsPath']) / 'produced-carton.pl'), str(output)],
        'perl': [result['applicationPerl']['executable'], *['-I' + root for root in result['libraryRoots']]],
        'metadata': [declared['toolSdk']['applicationPerl']['executable'], '-I' + declared['toolsPath'],
                     str(Path(declared['toolsPath']) / 'produced-metadata.pl'), str(output)],
    }
    for name, command in commands.items():
        body = '#!' + declared['runtimeShell'] + '\n'
        if name in {'carton', 'metadata'}:
            body += 'unset PERL5LIB PERLLIB PERL5OPT\nexport PERL_HASH_SEED=0 PERL_PERTURB_KEYS=0\n'
            body += 'export PATH=' + shlex.quote(declared['nativePath']) + ':"$PATH"\n'
            body += 'export SSL_CERT_FILE="${SSL_CERT_FILE:-' + declared['sslCertFile'] + '}"\n'
        body += 'exec ' + shlex.join(command) + ' "$@"\n'
        (programs / name).write_text(body)
        (programs / name).chmod(0o555)


if __name__ == '__main__':
    build(*sys.argv[1:])
