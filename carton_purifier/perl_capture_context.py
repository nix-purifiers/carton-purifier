# SPDX-License-Identifier: MIT
"""Retain production references; reconstruct authority from original Nix inputs."""
from pathlib import Path
import re

from perl_library import canonical, read_json, within

FORMAT = 'perl-library-capture-context-v1'
FIELDS = {'format', 'nativeMetadataPaths', 'moduleMappingFiles', 'xsProbeModules'}


def exact(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError('carton-purifier: unsupported ' + label + ' fields')


def canonical_file(value, roots=None):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError('carton-purifier: capture reference must be an absolute file path')
    actual = Path(value).resolve(strict=True)
    if str(actual) != value or not actual.is_file():
        raise ValueError('carton-purifier: aliased or non-file capture reference')
    if roots is not None:
        within(actual, roots)
    return str(actual)


def validate_context(context, roots=None):
    exact(context, FIELDS, 'capture context')
    if context['format'] != FORMAT:
        raise ValueError('carton-purifier: unsupported capture context format')
    for key in ['nativeMetadataPaths', 'moduleMappingFiles', 'xsProbeModules']:
        if not isinstance(context[key], list):
            raise ValueError('carton-purifier: capture context lists required')
    metadata = [canonical_file(path, roots) for path in context['nativeMetadataPaths']]
    mappings = []
    references = list(metadata)
    for record in context['moduleMappingFiles']:
        exact(record, ['mapping', 'evidence'], 'native mapping reference')
        current = {key: canonical_file(record[key], roots) for key in ['mapping', 'evidence']}
        references.extend(current.values())
        mappings.append(current)
    if len(set(references)) != len(references):
        raise ValueError('carton-purifier: duplicate capture references')
    probes = context['xsProbeModules']
    if any(not isinstance(name, str) or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*', name) is None for name in probes):
        raise ValueError('carton-purifier: invalid native capture probe name')
    if len(set(probes)) != len(probes):
        raise ValueError('carton-purifier: duplicate native capture probes')
    expected = {'format': FORMAT, 'nativeMetadataPaths': sorted(metadata),
                'moduleMappingFiles': sorted(mappings, key=canonical), 'xsProbeModules': sorted(probes)}
    if canonical(context) != canonical(expected):
        raise ValueError('carton-purifier: noncanonical capture context ordering')
    return expected


def capture(request):
    context = {'format': FORMAT,
               'nativeMetadataPaths': sorted(request['nativeMetadataPaths']),
               'moduleMappingFiles': sorted(request.get('moduleMappingFiles', []), key=canonical),
               'xsProbeModules': sorted(request.get('xsProbeModules', []))}
    return validate_context(context)


def reconstruct(declared, observation_path):
    # The records below are created by the owning Nix constructor from actual
    # producer.outputs/getAttr and Core identities, not loaded from this file.
    outputs = declared['producerOutputs']
    if not isinstance(outputs, list) or not outputs:
        raise ValueError('carton-purifier: original producer output descriptors required')
    roots, names = [], set()
    for record in outputs:
        exact(record, ['name', 'path', 'identity'], 'original producer output')
        if not isinstance(record['name'], str) or record['name'] in names:
            raise ValueError('carton-purifier: duplicate original producer output')
        names.add(record['name'])
        root = Path(record['path']).resolve(strict=True)
        if str(root) != record['path'] or not root.is_dir():
            raise ValueError('carton-purifier: aliased original producer output root')
        if any(root == other or root.is_relative_to(other) or other.is_relative_to(root) for other in roots):
            raise ValueError('carton-purifier: overlapping original producer output roots')
        roots.append(root)
    if Path(declared['producerPath']).resolve(strict=True) not in roots:
        raise ValueError('carton-purifier: declared producer is not an original output')
    location = canonical_file(observation_path, roots)
    observation = read_json(location)
    source = Path(declared['sourcePath']).resolve(strict=True)
    context = validate_context(observation['captureContext'], roots + [source])
    # Only three ancillary fields come from production. In particular, no SDK,
    # source/producer identity, command, allowedRoots or dependency declaration
    # can replace the constructor's original Nix-derived values.
    request = dict(declared)
    for key in ['nativeMetadataPaths', 'moduleMappingFiles', 'xsProbeModules']:
        request[key] = context[key]
    request['allowedRoots'] = list(dict.fromkeys([
        str(source), *[str(root) for root in roots],
        *[item['path'] for item in declared['runtimeInputPaths']],
        *declared.get('dependencyRoots', []),
    ]))
    return request, observation
