# SPDX-License-Identifier: MIT
package Carton::Purifier::ProducedProfile;
use strict;
use warnings;
use JSON::PP;
use CPAN::Meta::Requirements;
use Carton::Dist::Produced;
use Carton::Dist::SDK;
use Carton::Purifier::Requirements;
use Carton::Purifier::NativeContext;
use Carton::Snapshot;
use Menlo::CLI::Compat;

my $installed;
my @application_paths;

sub application_paths {
    die "carton-purifier: verified produced profile is not active\n" unless $installed;
    return @application_paths;
}

sub trace {
    return unless $ENV{CARTON_PURIFIER_PRODUCED_TRACE};
    open my $file, '>>', $ENV{CARTON_PURIFIER_PRODUCED_TRACE}
        or die "carton-purifier: append native produced trace: $!";
    print {$file} JSON::PP->new->canonical->encode($_[0]), "\n";
    close $file or die "carton-purifier: close native produced trace: $!";
}

# Only the owning profile launcher calls this, after replaying the original
# catalogs, producer payloads and selected application SDK. This is separate
# from the legacy SDK patch and never changes CPAN distributions or indexes.
sub install {
    my ($profile) = @_;
    die "carton-purifier: produced profile already installed\n" if $installed++;
    Carton::Purifier::NativeContext::install($profile);
    my $providers = $profile->{providers};
    my %ambiguous = map { $_ => 1 } @{$profile->{ambiguousSdkPackages}};
    my @roots = @{$profile->{libraryRoots}};
    my @sdk_inc = @{$profile->{sdkInc}};
    @application_paths = (@roots, @sdk_inc);
    $ENV{PERL5LIB} = join ':', @roots, @sdk_inc;
    delete $ENV{PERL5OPT};
    my %dist;
    my $sdk = Carton::Dist::SDK->new(%{$profile->{sdkNode}});
    for my $row (@{$profile->{distributions}}) {
        my $requirements = CPAN::Meta::Requirements->new;
        for my $set (@{$row->{requirementSets}}) {
            $requirements->add_string_requirement($_, $set->{$_}) for sort keys %$set;
        }
        my $distribution = Carton::Dist::Produced->new(%$row, requirements => $requirements->as_string_hash);
        for my $module (keys %{$distribution->provides}) {
            die "carton-purifier: duplicate produced distribution package\n" if $dist{$module};
            $dist{$module} = $distribution;
        }
    }
    my $check = Menlo::CLI::Compat->can('check_module');
    my $setup = Menlo::CLI::Compat->can('setup_local_lib');
    my $find = Carton::Snapshot->can('find_or_core');
    no warnings 'redefine';
    *Menlo::CLI::Compat::check_module = sub {
        my ($self, $module, $constraint) = @_;
        die "carton-purifier: ambiguous selected SDK package version: $module\n" if $ambiguous{$module};
        return $check->(@_) unless exists $providers->{$module};
        my $version = $providers->{$module}{nativeVersion};
        my $requirements = CPAN::Meta::Requirements->new;
        $requirements->add_string_requirement($module, $constraint || '0');
        die "carton-purifier: provided package fails native constraint: $module\n"
            unless $requirements->accepts_module($module, $version);
        trace({hook => 'check_module', module => $module, nativeVersion => $version,
               constraint => $requirements->requirements_for_module($module)});
        $self->{local_versions}{$module} = $version;
        return (1, defined($version) && length($version) ? $version : 'undef');
    };
    *Menlo::CLI::Compat::unsatisfied_deps = sub {
        my ($self, @deps) = @_;
        die "carton-purifier: ambiguous selected SDK package version: " . $_->module . "\n"
            for grep { $_->is_requirement && $ambiguous{$_->module} } @deps;
        my @failed = Carton::Purifier::Requirements::unsatisfied($providers, $self->search_inc, @deps);
        trace({hook => 'unsatisfied_deps', provided => [map {
            +{module => $_->module, constraint => $_->requires_version || '0',
              nativeVersion => $providers->{$_->module}{nativeVersion}}
        } grep { $_->is_requirement && exists $providers->{$_->module} } @deps], failed => \@failed});
        return @failed;
    };
    *Menlo::CLI::Compat::setup_local_lib = sub {
        my ($self) = @_;
        my $context = wantarray;
        my (@values, $value);
        if (!defined $context) { $setup->(@_); }
        elsif ($context) { @values = $setup->(@_); }
        else { $value = $setup->(@_); }
        # Native -L local directories retain their positions. Tooling modules
        # in Carton's process @INC must not become application dependencies.
        my @local = @{$self->{search_inc}}[0, 1];
        $self->{search_inc} = [@roots, @local, @sdk_inc];
        $ENV{PERL5LIB} = join ':', @roots, @local, @sdk_inc;
        return !defined($context) ? () : $context ? @values : $value;
    };
    *Carton::Snapshot::find_or_core = sub {
        my ($self, $module) = @_;
        my $native = $find->(@_);
        if ($dist{$module}) {
            die "carton-purifier: produced package collides with native snapshot/core: $module\n" if $native;
            return $dist{$module};
        }
        if ($sdk->provides_module($module)) {
            die "carton-purifier: SDK package collides with native CPAN snapshot: $module\n"
                if $native && !$native->is_core;
            if ($native) {
                my $expected = $sdk->version_for($module);
                my $actual = $native->version_for($module);
                my $equal = !defined($expected) && !defined($actual);
                if (defined($expected) && defined($actual)) {
                    my $requirements = CPAN::Meta::Requirements->new;
                    $requirements->add_string_requirement($module, '== ' . $expected);
                    $equal = $requirements->accepts_module($module, $actual);
                }
                my $json = JSON::PP->new->canonical;
                die "carton-purifier: selected SDK contradicts native core package: $module\n"
                    unless $equal && $json->encode($providers->{$module}{providerIdentity})
                        eq $json->encode($profile->{sdkNode}{baseIdentity});
            }
            return $sdk unless $native;
        }
        return $native;
    };
    return;
}

1;
