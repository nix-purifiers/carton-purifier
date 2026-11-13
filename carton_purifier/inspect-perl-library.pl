# SPDX-License-Identifier: MIT
use strict;
use warnings;
use Config;
use Module::Metadata;
use JSON::PP;
use Cwd qw(abs_path);
use Digest::SHA;
use DynaLoader ();

my ($request_path) = @ARGV;
open my $request_file, '<', $request_path or die $!;
my $request = JSON::PP->new->decode(do { local $/; <$request_file> });
# Record the original SDK before loading explicitly requested producer modules.
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
my @xs_loads;
for my $module (@{$request->{xsProbeModules} || []}) {
    die "carton-purifier: invalid native probe module\n"
        unless $module =~ /\A[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*\z/;
    my $lookup = $module; $lookup =~ s{::}{/}g; $lookup .= '.pm';
    local @INC = (@{$request->{libraryRoots}}, @INC);
    require $lookup;
    die "carton-purifier: native probe has no actual module origin\n" unless -f $INC{$lookup};
    my @expected = grep { $_->{path} eq $lookup } @{$request->{moduleFiles}};
    die "carton-purifier: native probe did not load its original installed producer module\n"
        unless @expected == 1 && abs_path($expected[0]->{file}) eq abs_path($INC{$lookup});
    my @objects;
    my %seen;
    for my $object (@DynaLoader::dl_shared_objects) {
        my $actual = abs_path($object);
        die "carton-purifier: missing loaded native object\n" unless defined $actual && -f $actual;
        next if $seen{$actual}++;
        open my $input, '<', $actual or die $!; binmode $input;
        push @objects, {path => $actual, sha256 => Digest::SHA->new(256)->addfile($input)->hexdigest};
    }
    my @loaded;
    for my $name (sort keys %INC) {
        die "carton-purifier: unsupported native probe loader origin\n" if ref $INC{$name};
        next unless -f $INC{$name};
        open my $input, '<', $INC{$name} or die $!; binmode $input;
        push @loaded, {name => $name, file => abs_path($INC{$name}),
            sha256 => Digest::SHA->new(256)->addfile($input)->hexdigest};
    }
    my $module_version;
    { no strict 'refs'; $module_version = ${$module . '::VERSION'}; }
    push @xs_loads, {requestedModule => $module, moduleFile => abs_path($INC{$lookup}),
        nativeVersion => defined($module_version) ? "$module_version" : undef,
        sharedObjects => [sort {$a->{path} cmp $b->{path}} @objects], loadedModules => \@loaded};
}
# Upstream metadata may compute VERSION from a genuinely loaded prerequisite
# (for example $Thrift::VERSION). Explicit native probes run unchanged code
# before Module::Metadata evaluates that expression; null versions stay null.
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
my @metadata_modules;
for my $name (sort keys %INC) {
    my $file = $INC{$name};
    die "carton-purifier: unsupported metadata loader origin\n"
        if ref($file) || !defined($file) || !-f $file;
    open my $input, '<', $file or die $!; binmode $input;
    push @metadata_modules, {name => $name, file => abs_path($file),
        sha256 => Digest::SHA->new(256)->addfile($input)->hexdigest};
}
my @metadata_objects;
my %metadata_objects_seen;
for my $object (@DynaLoader::dl_shared_objects) {
    my $actual = abs_path($object);
    die "carton-purifier: missing metadata native object\n" unless defined($actual) && -f $actual;
    next if $metadata_objects_seen{$actual}++;
    open my $input, '<', $actual or die $!; binmode $input;
    push @metadata_objects, {path => $actual, sha256 => Digest::SHA->new(256)->addfile($input)->hexdigest};
}
print JSON::PP->new->canonical->encode({
    baseExecutable => abs_path($^X), config => { map { $_ => $Config{$_} } keys %Config },
    inc => \@inc, moduleOrigins => \@origins, moduleFiles => \@files, xsLoads => \@xs_loads,
    metadataLoads => {modules => \@metadata_modules,
        sharedObjects => [sort {$a->{path} cmp $b->{path}} @metadata_objects]},
});
