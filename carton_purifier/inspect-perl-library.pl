# SPDX-License-Identifier: MIT
use strict;
use warnings;
use Config;
use Module::Metadata;
use JSON::PP;
use Cwd qw(abs_path);
use Digest::SHA;

my ($request_path) = @ARGV;
open my $request_file, '<', $request_path or die $!;
my $request = JSON::PP->new->decode(do { local $/; <$request_file> });
my @files;
for my $entry (@{$request->{moduleFiles}}) {
    my $meta = Module::Metadata->new_from_file($entry->{file})
        or die "carton-purifier: cannot inspect actual module $entry->{file}\n";
    my @packages;
    for my $package (sort $meta->packages_inside) {
        next unless $meta->is_indexable($package);
        my $version = $meta->version($package);
        push @packages, { name => $package, version => defined($version) ? "$version" : undef };
    }
    push @files, { %$entry, packages => \@packages };
}
my @inc;
for my $path (@INC) {
    die "carton-purifier: unsupported application Perl loader hook\n" if ref $path;
    push @inc, $path;
}
my @origins;
for my $module (sort keys %INC) {
    my $file = $INC{$module};
    die "carton-purifier: unsupported loaded module origin\n" if ref $file;
    next unless -f $file;
    open my $input, '<', $file or die $!;
    binmode $input;
    push @origins, { module => $module, file => abs_path($file),
        sha256 => Digest::SHA->new(256)->addfile($input)->hexdigest };
}
print JSON::PP->new->canonical->encode({
    baseExecutable => abs_path($^X), config => { map { $_ => $Config{$_} } keys %Config },
    inc => \@inc, moduleOrigins => \@origins, moduleFiles => \@files,
});
