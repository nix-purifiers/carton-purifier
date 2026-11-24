# SPDX-License-Identifier: MIT
use strict;
use warnings;
use ExtUtils::MakeMaker ();
use ExtUtils::Install ();
use File::Temp qw(tempdir);
use Cwd qw(getcwd);
use JSON::PP;
use Digest::SHA qw(sha256_hex);
my $native_flush=\&ExtUtils::MakeMaker::flush;
my $native_copy=\&ExtUtils::Install::_copy;
my $folder=tempdir(CLEANUP=>1);
$ENV{CARTON_PURIFIER_MAKER_CAPTURE}="$folder/events.jsonl";
require Carton::Purifier::MakeMaker;
my $json=JSON::PP->new->canonical;
sub bytes {open my $f,'<',$_[0] or die $!;binmode $f;return do {local $/;<$f>}}
sub invoke {
    my ($call,$context,@args)=@_;
    if ($context eq 'list') {my @value=$call->(@args);return \@value;}
    if ($context eq 'scalar') {my $value=$call->(@args);return [$value];}
    $call->(@args);return [];
}
my $original_cwd=getcwd();chdir $folder or die $!;
# This is an owned native MakeMaker package fixture, not SDK metadata.
my $mm=ExtUtils::MakeMaker::WriteMakefile(NAME=>'Owned::Capture::Context',VERSION=>'1.0.0',PM=>{});
my @results;
for my $context (qw(void scalar list)) {
    my $before=invoke($native_flush,$context,$mm);my $native_makefile=bytes('Makefile');
    my $after=invoke(\&ExtUtils::MakeMaker::flush,$context,$mm);
    die 'native flush return changed' unless $json->encode($before) eq $json->encode($after);
    die 'native flush Makefile changed' unless $native_makefile eq bytes('Makefile');
    open my $source,'>',"source-$context" or die $!;print {$source} "owned native copy $context\n";close $source;
    my @args=("source-$context","target-$context",0,0);
    my $copy_before=invoke($native_copy,$context,@args);my $native_bytes=bytes("target-$context");
    unlink "target-$context" or die $!;
    my $copy_after=invoke(\&ExtUtils::Install::_copy,$context,@args);
    die 'native copy return changed' unless $json->encode($copy_before) eq $json->encode($copy_after);
    die 'native copy arguments/output changed' unless $native_bytes eq bytes("target-$context") && $native_bytes eq bytes("source-$context");
    push @results,{context=>$context,flushReturn=>$after,copyReturn=>$copy_after,makefileSha256=>sha256_hex($native_makefile),copySha256=>sha256_hex($native_bytes)};
}
my @events=map {$json->decode($_)} split /\n/,bytes('events.jsonl');
for my $context (qw(void scalar list)) {
    die 'native context not recorded' unless grep {$_->{kind} eq 'native-install-copy' && $_->{context} eq $context} @events;
    die 'native flush context not recorded' unless grep {$_->{kind} eq 'native-MM-flush' && $_->{context} eq $context} @events;
}
chdir $original_cwd or die $!;
print 'CONTEXT_PROOF '.$json->encode({scope=>'actual selected native Maker flush and Install copy scalar/list/void equivalence',results=>\@results,eventCount=>scalar @events})."\n";
