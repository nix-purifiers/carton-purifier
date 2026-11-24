# SPDX-License-Identifier: MIT
use strict;
use warnings;
use JSON::PP;
use Carton::Purifier::ProducedProfile;
use Carton::Snapshot;

my ($profile_path, $snapshot_path, $mode) = @ARGV;
open my $file, '<', $profile_path or die $!;
my $json = JSON::PP->new->canonical;
my $profile = $json->decode(do { local $/; <$file> });
if ($mode eq 'owner') {
    die 'control requires an actual distinct SDK wrapper identity'
        if $json->encode($profile->{sdkNode}{identity}) eq $json->encode($profile->{sdkNode}{baseIdentity});
    # Use another real Nix input identity from this selected SDK, not an
    # invented version, path or derivation, to test the core owner refusal.
    $profile->{providers}{strict}{providerIdentity} = $profile->{sdkNode}{identity};
}
Carton::Purifier::ProducedProfile::install($profile);
my $snapshot = Carton::Snapshot->new(path => $snapshot_path);
$snapshot->load;
my @cpan_before = map $_->pathname, $snapshot->distributions;
if ($mode eq 'collision') {
    eval { $snapshot->find_or_core('Try::Tiny') };
    die 'actual SDK/CPAN collision accepted' unless $@ =~ /SDK package collides with native CPAN snapshot/;
} elsif ($mode eq 'owner') {
    eval { $snapshot->find_or_core('strict') };
    die 'nonowning original SDK identity accepted as core owner' unless $@ =~ /selected SDK contradicts native core package/;
} else {
    for my $module ('Class::Accessor', 'Bit::Vector') {
        my $node = $snapshot->find_or_core($module) or die 'actual SDK node missing';
        die 'SDK falsely classified as core' if $node->is_core;
        die 'SDK acquired a CPAN pathname' if $node->can('pathname');
        die 'wrong node type' unless $node->isa('Carton::Dist::SDK');
        die 'SDK identity changed' unless $json->encode($node->identity) eq $json->encode($profile->{sdkNode}{identity});
        die 'original SDK closure lost' unless $json->encode($node->runtime_inputs) eq $json->encode($profile->{sdkNode}{runtimeInputs});
        die 'native SDK package version changed' unless $json->encode($node->version_for($module)) eq $json->encode($profile->{providers}{$module}{nativeVersion});
        die 'SDK CPAN edges invented' if $node->requirements->required_modules;
    }
    die 'native core classification changed' unless $snapshot->find_or_core('strict')->is_core;
}
my @cpan_after = map $_->pathname, $snapshot->distributions;
die 'SDK nodes changed native CPAN distributions' unless $json->encode(\@cpan_before) eq $json->encode(\@cpan_after);
print $json->encode({mode => $mode, passed => JSON::PP::true, actualNativeCPANPaths => \@cpan_after}), "\n";
