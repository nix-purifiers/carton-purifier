# SPDX-License-Identifier: MIT
# Native framework hook unit: the class is inspected from a real generator
# output; full generator catalog composition is outside this unit.
use strict;
use warnings;
use JSON::PP;
use Module::Metadata;
use Digest::SHA qw(sha256_hex);
use File::Temp qw(tempdir);
use Carton::Purifier::ProducedProfile;
use Carton::Tree;
use Carton::CPANfile;
use Menlo::Dependency;

my ($profile_path, $source) = @ARGV;
open my $file, '<', $profile_path or die $!;
my $profile = JSON::PP->new->decode(do { local $/; <$file> });
my $metadata = Module::Metadata->new_from_file($source) or die 'missing actual generated source';
my $class = 'SchemaMain::Envelope';
die 'missing native declared class' unless grep { $_ eq $class } $metadata->packages_inside;
my $version = $metadata->version($class);
die 'expected native null version' if defined $version;
die 'unexpected fabricated class loader' if $source =~ m{/Envelope\.pm$};
$profile->{providers}{$class} = {nativeVersion => $version};
push @{$profile->{distributions}}, {identity => sha256_hex($source), provides => {$class => {version => $version}}, requirementSets => []};

my $menlo = Menlo::CLI::Compat->new;
$menlo->{search_inc} = [@INC];
my @native_missing = $menlo->unsatisfied_deps(Menlo::Dependency->from_versions({$class => '0'}));
die 'native filename control unexpectedly passes' unless @native_missing;
my @residual = sort $menlo->unsatisfied_deps(Menlo::Dependency->from_versions({'Owned::Missing::Residual' => '0'}));
Carton::Purifier::ProducedProfile::install($profile);
my ($ok) = $menlo->check_module($class, '0');
die 'provided class check rejected' unless $ok;
my @failed = $menlo->unsatisfied_deps(Menlo::Dependency->from_versions({$class => '0'}));
die 'provided class final check rejected' if @failed;
my @mixed = sort $menlo->unsatisfied_deps(Menlo::Dependency->from_versions({$class => '0', 'Owned::Missing::Residual' => '0'}));
die 'native residual check changed' unless JSON::PP->new->canonical->encode(\@mixed) eq JSON::PP->new->canonical->encode(\@residual);
eval { $menlo->check_module($class, '1') };
die 'native null version accepted positive constraint' unless $@ =~ /fails native constraint/;
@failed = $menlo->unsatisfied_deps(Menlo::Dependency->from_versions({$class => '1'}));
die 'final check accepted positive constraint' unless @failed;
my $folder = tempdir(CLEANUP => 1);
open my $cpanfile, '>', "$folder/cpanfile" or die $!;
print {$cpanfile} "requires '$class', '0';\n";
close $cpanfile;
my $parsed = Carton::CPANfile->new(path => "$folder/cpanfile");
$parsed->load;
my $snapshot = Carton::Snapshot->new(path => "$folder/cpanfile.snapshot");
my $tree = Carton::Tree->new(cpanfile => $parsed, snapshot => $snapshot);
die 'actual tree lost provided class' unless defined $tree->merged_requirements->requirements_for_module($class);
die 'provided entered CPAN distributions' if $snapshot->distributions;
die 'produced distribution exposes fake CPAN pathname' if $snapshot->find_or_core($class)->can('pathname');
print JSON::PP->new->canonical->encode({scope => 'native profile hook unit with real generated class metadata', source => $source, nativeVersion => $version, nativeFilenameLookupFails => JSON::PP::true, bothProvidedHooksPass => JSON::PP::true, positiveConstraintRejectedByBothHooks => JSON::PP::true, residualNativeCheckPreserved => JSON::PP::true, actualTreePass => JSON::PP::true, nativeCPANDistributions => 0}), "\n";
