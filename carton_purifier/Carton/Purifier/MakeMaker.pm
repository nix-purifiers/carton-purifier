# SPDX-License-Identifier: MIT
package Carton::Purifier::MakeMaker;
use strict;
use warnings;
use ExtUtils::MakeMaker ();
use ExtUtils::Install ();
use JSON::PP;
use Cwd qw(abs_path getcwd);
use Digest::SHA;
sub sha {
    my ($path)=@_;open my $file,'<',$path or die $!;binmode $file;
    return Digest::SHA->new(256)->addfile($file)->hexdigest;
}
sub base_executable {
    my $executable = $^X;
    if ($executable !~ m{/}) {
        my @paths = grep {-f $_ && -x $_} map {(length($_) ? $_ : ".")."/$executable"} split /:/, $ENV{PATH};
        die 'native Perl executable is not on PATH' unless @paths;
        $executable = $paths[0];
    }
    my $actual = abs_path($executable);
    die 'native Perl executable is missing' unless defined $actual && -f $actual && -x $actual;
    return $actual;
}
sub native_sources {
    my @sources;
    for my $module (sort grep { /\AExtUtils\/(?:MakeMaker|Install|MM_[^\/]+)\.pm\z/ } keys %INC) {
        push @sources, {module=>$module,file=>abs_path($INC{$module}),sha256=>sha($INC{$module})};
    }
    return \@sources;
}
sub emit {
    my ($event)=@_;my $path=$ENV{CARTON_PURIFIER_MAKER_CAPTURE} or die 'missing native probe destination';
    open my $output,'>>',$path or die $!;print {$output} JSON::PP->new->canonical->encode($event)."\n";close $output or die $!;
}
sub delegate {
    my ($native,$after,$context,@args)=@_;
    if (!defined $context) {$native->(@args);$after->(@args);return;}
    if ($context) {my @result=$native->(@args);$after->(@args);return @result;}
    my $result=$native->(@args);$after->(@args);return $result;
}
my $flush=\&ExtUtils::MakeMaker::flush;
my $copy=\&ExtUtils::Install::_copy;
{
 no warnings 'redefine';
 *ExtUtils::MakeMaker::flush=sub {
    my $context=wantarray;
    my ($mm)=@_;
    # Native flush discards child-MM fields after writing. Retain its actual
    # finalized input map before delegating, without changing the MM object.
    my %pm=%{$mm->{PM}};
    my %variables;
    for my $key (qw(INST_LIB INST_ARCHLIB INST_LIBDIR INST_ARCHLIBDIR INSTALL_BASE INSTALLDIRS INSTALLSITELIB INSTALLSITEARCH INSTALLPRIVLIB INSTALLARCHLIB MAKEFILE)) {
        $variables{$key}=$mm->{$key};
    }
    return delegate($flush,sub {
        emit({kind=>'native-MM-flush',cwd=>getcwd(),pm=>\%pm,variables=>\%variables,
            makerVersion=>$ExtUtils::MakeMaker::VERSION,makefileSha256=>sha($variables{MAKEFILE}),
            baseExecutable=>base_executable(),nativeSources=>native_sources(),context=>!defined($context)?'void':$context?'list':'scalar'});
    },$context,@_);
 };
 *ExtUtils::Install::_copy=sub {
    my $context=wantarray;
    return delegate($copy,sub {
        my ($from,$to,$verbose,$dry_run)=@_;
        emit({kind=>'native-install-copy',cwd=>getcwd(),from=>abs_path($from),to=>abs_path($to),
            baseExecutable=>base_executable(),nativeSources=>native_sources(),context=>!defined($context)?'void':$context?'list':'scalar',
            dryRun=>$dry_run?JSON::PP::true:JSON::PP::false,sourceSha256=>sha($from),destinationSha256=>sha($to)});
    },$context,@_);
 };
}
1;
