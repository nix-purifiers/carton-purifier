# SPDX-License-Identifier: MIT
"""Scope native Carton exec to the verified produced-library environment."""
from pathlib import Path
import sys

path = Path(sys.argv[1]) / 'lib/Carton/CLI.pm'
text = path.read_text()
old = '    local $ENV{PERL5LIB} = "$path/lib/perl5";'
new = ('    local $ENV{PERL5LIB} = join ":", "$path/lib/perl5", '
       'Carton::Purifier::ProducedProfile::application_paths();')
if text.count(old) != 1:
    raise ValueError('carton-purifier: unsupported native produced-profile exec boundary')
path.write_text(text.replace(old, new))
