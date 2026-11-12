# SPDX-License-Identifier: MIT
from pathlib import Path
import sys

root = Path(sys.argv[1])
path = root / "lib/Carton/Environment.pm"
text = path.read_text()
old = '    Carton::Snapshot->new(path => $self->cpanfile . ".snapshot");'
new = '    Carton::Snapshot->new(path => $ENV{CARTON_PURIFIER_SNAPSHOT} || $self->cpanfile . ".snapshot");'
assert text.count(old) == 1
text = text.replace(old, new)
old = "sub _build_vendor_cache {\n    my $self = shift;"
new = (
    old
    + "\n    return Path::Tiny->new($ENV{CARTON_PURIFIER_VENDOR_CACHE}) if $ENV{CARTON_PURIFIER_VENDOR_CACHE};"
)
assert text.count(old) == 1
path.write_text(text.replace(old, new))
path = root / "lib/Carton/CLI.pm"
text = path.read_text()
old = """    if ($deployment && !$env->snapshot->loaded) {"""
new = (
    """    if ($ENV{CARTON_PURIFIER_FROZEN}) {
        $self->cmd_check("--cpanfile", "@{[$env->cpanfile]}");
        $self->print("Complete! Modules were installed into @{[$env->install_path]}\\n", SUCCESS);
        return;
    }

"""
    + old
)
assert text.count(old) == 1
path.write_text(text.replace(old, new))
