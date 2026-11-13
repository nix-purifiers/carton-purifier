# SPDX-License-Identifier: MIT
use strict;
use warnings;
use Module::CPANfile;
use Module::Metadata;
use Carton::Purifier::CPANfile;
use File::Temp qw(tempdir);
use JSON::PP;
use Digest::SHA qw(sha256_hex);
my ($native_source) = @ARGV;
my $metadata = Module::Metadata->new_from_file($native_source) or die 'missing real generated metadata';
my $package = 'SchemaMain::Envelope';
die 'native generated class missing' unless grep { $_ eq $package } $metadata->packages_inside;
my $version = $metadata->version($package);
die 'expected actual unversioned generated class' if defined $version;
my $providers = { $package => {
    nativeVersion => $version, providerIdentity => sha256_hex($native_source),
    declaredIn => [{ root => 'lib/perl5', path => 'SchemaMain/Types.pm' }],
}};
my $folder = tempdir(CLEANUP => 1);
my $counter=0;
sub load_text {
    my ($text)=@_;my $path="$folder/fixture-".$counter++.'.cpanfile';
    open my $out,'>',$path or die $!;print {$out} $text;close $out;
    return Module::CPANfile->load($path);
}
my $selection={selectedFeatures=>[],wantedPhases=>[qw(build test runtime develop)],installTypes=>['requires']};
my $text=<<'DSL';
mirror 'https://cpan.metacpan.org';
requires 'SchemaMain::Envelope', '0';
requires 'Residual::Runtime', '>= 1', git => 'https://example.invalid/source.git', ref => 'owned-fixture';
recommends 'Residual::Recommended', '0';
suggests 'Residual::Suggested', '0';
conflicts 'Residual::Conflict', '< 1';
on configure => sub {requires 'Residual::Configure', '0';};
on build => sub {requires 'Residual::Build', '0';};
on test => sub {requires 'Residual::Test', '0';};
on develop => sub {requires 'Residual::Develop', '0';};
feature 'disabled', 'Preserve native inactive feature' => sub {requires 'SchemaMain::Envelope', '>= 999';};
DSL
my $file=load_text($text);
my $bound=Carton::Purifier::CPANfile::bind($file,$providers,$selection);
die 'missing native binding' unless @{$bound->{bindings}}==1 && !defined $bound->{bindings}[0]{nativeVersion};
Carton::Purifier::CPANfile::save_verified($bound,"$folder/effective.cpanfile");
my @results=({case=>'actual-unversioned-class-in-Types-and-full-residual-DSL',result=>'PASS'});
my @cases=(
 ['active-feature-version', $file, {%$selection,selectedFeatures=>['disabled']},'provided version does not satisfy'],
 ['unversioned-minimum',load_text("requires 'SchemaMain::Envelope','1';"),$selection,'provided version does not satisfy'],
 ['bound-source-options',load_text("requires 'SchemaMain::Envelope','0',git=>'https://example.invalid/owned.git';"),$selection,'bound source options'],
 ['active-conflict',load_text("conflicts 'SchemaMain::Envelope','0';"),$selection,'provided version conflicts'],
 ['lossy-native-source-options',load_text("requires 'Residual::Repeated','0',git=>'https://example.invalid/a';on test=>sub {requires 'Residual::Repeated','0',git=>'https://example.invalid/b';};"),$selection,'serializer loses'],
);
for my $case (@cases) {
 my ($name,$input,$selection,$expected)=@$case;
 my $ok=eval {my $b=Carton::Purifier::CPANfile::bind($input,$providers,$selection);Carton::Purifier::CPANfile::save_verified($b,"$folder/rejected.cpanfile");1};
 die "accepted $name" if $ok;die $@ unless index($@,$expected)>=0;
 push @results,{case=>$name,result=>'REJECTED',diagnostic=>"$@"};
}
print JSON::PP->new->canonical->pretty->encode({scope=>'native DSL binding unit with actual generated module metadata; not framework integration',nativeSource=>$native_source,nativeVersion=>$version,results=>\@results});
