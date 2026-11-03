# SPDX-License-Identifier: MIT
use strict;
use warnings;
use Carton::Snapshot;
use Carton::CPANfile;
use Carton;
use JSON::PP;
use Config;
my $snapshot = Carton::Snapshot->new(path => $ARGV[0]);
$snapshot->load;
if (@ARGV > 1) {
    my $cpanfile = Carton::CPANfile->new(path => $ARGV[2]);
    $cpanfile->load;
    $snapshot->find_installs($ARGV[1], $cpanfile->requirements);
}
my @distributions = map {
    my $dist = $_;
    my %provides = map {
        my $module = $_;
        ($module => {version => defined($dist->provides->{$module}{version}) ?
            ''. $dist->provides->{$module}{version} : 'undef'})
    } keys %{$dist->provides};
    +{name => $dist->name, pathname => $dist->pathname, provides => \%provides,
      requirements => $dist->requirements->as_string_hash}
} sort {$a->pathname cmp $b->pathname} $snapshot->distributions;
print JSON::PP->new->canonical->encode({formatVersion=>$snapshot->version,
    distributions=>\@distributions,
    toolVersions=>{carton=>"$Carton::VERSION",perl=>$Config{version},archname=>$Config{archname}}});
