# SPDX-License-Identifier: MIT
"""Observe native phase frames and bind only the actual root cpanfile."""
from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'lib/Menlo/CLI/Compat.pm'
text = path.read_text()
edits = {
    '    $self->upgrade_toolchain(\\@config_deps);':
        '    Carton::Purifier::NativeContext::record($self, $dist, $depth, "configure", ["configure"], [], \\@config_deps);',
    '    my @deps = $self->find_prereqs($dist);':
        '    Carton::Purifier::NativeContext::record($self, $dist, $depth, "post-configure", $dist->{want_phases}, $dist->{carton_purifier_features} || [], \\@deps);',
    '        my @features = $self->configure_features($dist, $dist->{cpanfile}->features);':
        '        Carton::Purifier::NativeContext::bind_root($self, $dist, \\@features);',
    '    my @features = $self->configure_features($dist, $meta->features);':
        '    Carton::Purifier::NativeContext::features($dist, \\@features);',
}
for old, addition in edits.items():
    if text.count(old) != 1:
        raise ValueError('carton-purifier: unsupported native Menlo phase boundary: ' + old)
    text = text.replace(old, old + '\n' + addition)
path.write_text(text)
