# SPDX-License-Identifier: MIT
package Carton::Purifier::CPANfile;
use strict;
use warnings;
use Storable qw(dclone);
use JSON::PP;
use Module::CPANfile;
use CPAN::Meta::Requirements;

my $json = JSON::PP->new->canonical;
my %phase = map { $_ => 1 } qw(runtime configure build test develop);
my %type = map { $_ => 1 } qw(requires recommends suggests conflicts);

sub keys_are {
    my ($value, $allowed, $where) = @_;
    die "carton-purifier: unsupported native $where object\n" unless ref($value);
    my %allowed = map { $_ => 1 } @$allowed;
    die "carton-purifier: unsupported native $where field $_\n" for grep { !$allowed{$_} } keys %$value;
}

sub model {
    my ($file) = @_;
    die "carton-purifier: unexpected native cpanfile class\n" unless ref($file) eq 'Module::CPANfile';
    keys_are($file, [qw(_mirrors _prereqs)], 'cpanfile');
    my $prereqs = $file->{_prereqs};
    die "carton-purifier: unexpected native prereqs class\n" unless ref($prereqs) eq 'Module::CPANfile::Prereqs';
    keys_are($prereqs, [qw(prereqs features cpanmeta)], 'prereqs');
    my @edges;
    for my $feature (sort keys %{$prereqs->{prereqs}}) {
        die "carton-purifier: undeclared native feature $feature\n"
            if length($feature) && !exists $prereqs->{features}{$feature};
        for my $edge (@{$prereqs->{prereqs}{$feature}}) {
            die "carton-purifier: unexpected native prerequisite class\n" unless ref($edge) eq 'Module::CPANfile::Prereq';
            keys_are($edge, [qw(feature phase type module requirement)], 'prerequisite');
            die "carton-purifier: inconsistent native feature\n" unless ($edge->feature || '') eq $feature;
            die "carton-purifier: unsupported native phase/type\n" unless $phase{$edge->phase} && $type{$edge->type};
            my $requirement = $edge->requirement;
            die "carton-purifier: unexpected native requirement class\n" unless ref($requirement) eq 'Module::CPANfile::Requirement';
            keys_are($requirement, [qw(name version options)], 'requirement');
            die "carton-purifier: inconsistent native requirement module\n" unless $requirement->name eq $edge->module;
            my $native = CPAN::Meta::Requirements->new;
            $native->add_string_requirement($edge->module, $requirement->version);
            # JSON encoding rejects executable/blessed options instead of dropping them.
            my $options = $json->decode($json->encode($requirement->options));
            push @edges, {
                feature => $feature, phase => $edge->phase, type => $edge->type,
                module => $edge->module, constraint => $native->requirements_for_module($edge->module),
                options => $options,
            };
        }
    }
    for my $feature (values %{$prereqs->{features}}) {
        keys_are($feature, ['description'], 'feature');
        die "carton-purifier: missing native feature description\n" unless defined $feature->{description} && !ref($feature->{description});
    }
    @edges = sort { $json->encode($a) cmp $json->encode($b) } @edges;
    return {
        mirrors => dclone($file->mirrors), features => dclone($prereqs->{features}), edges => \@edges,
    };
}

sub bind {
    my ($file, $providers, $selection) = @_;
    # The caller obtains this selection from actual native framework invocations;
    # the binding layer never guesses which optional features or phases are active.
    my %active_features = map { $_ => 1 } @{$selection->{selectedFeatures}};
    my %active_phases = map { $_ => 1 } @{$selection->{wantedPhases}};
    my %active_types = map { $_ => 1 } @{$selection->{installTypes}};
    die "carton-purifier: unsupported active install type\n" if grep { !$type{$_} } keys %active_types;
    die "carton-purifier: unsupported active phase\n" if grep { !$phase{$_} } keys %active_phases;
    die "carton-purifier: unknown active feature\n" if grep { !exists $file->{_prereqs}{features}{$_} } keys %active_features;
    my $original = model($file);
    my $effective = dclone($file);
    my @bindings;
    my @expected;
    for my $edge (@{$original->{edges}}) {
        my $provider = $providers->{$edge->{module}};
        my $active = (!length($edge->{feature}) || $active_features{$edge->{feature}})
            && $active_phases{$edge->{phase}};
        my $requires = $edge->{type} eq 'requires' && $active_types{requires};
        my $conflicts = $edge->{type} eq 'conflicts';
        if ($provider && $active && ($requires || $conflicts)) {
            die "carton-purifier: bound source options require a verified origin adapter: $edge->{module}\n"
                if keys %{$edge->{options}};
            my $native = CPAN::Meta::Requirements->new;
            $native->add_string_requirement($edge->{module}, $edge->{constraint});
            my $accepts = $native->accepts_module($edge->{module}, $provider->{nativeVersion});
            die "carton-purifier: provided version does not satisfy $edge->{module}\n" if $requires && !$accepts;
            die "carton-purifier: provided version conflicts with $edge->{module}\n" if $conflicts && $accepts;
            push @bindings, {
                edge => dclone($edge), providerIdentity => $provider->{providerIdentity},
                package => $edge->{module}, nativeVersion => $provider->{nativeVersion},
                declaredIn => dclone($provider->{declaredIn}),
                action => $requires ? 'requires-removed' : 'conflict-checked',
            };
            next if $requires;
        }
        push @expected, $edge;
    }
    # Filter native objects by exact canonical edge. A multiset preserves duplicate
    # declarations until the native round-trip detects whether they are representable.
    my %remove;
    $remove{$json->encode($_->{edge})}++ for grep { $_->{action} eq 'requires-removed' } @bindings;
    for my $feature (keys %{$effective->{_prereqs}{prereqs}}) {
        my @kept;
        for my $edge (@{$effective->{_prereqs}{prereqs}{$feature}}) {
            my $single = dclone($effective);
            $single->{_prereqs}{prereqs} = { $feature => [$edge] };
            delete $single->{_prereqs}{cpanmeta};
            my $key = $json->encode(model($single)->{edges}[0]);
            if ($remove{$key}) { $remove{$key}--; } else { push @kept, $edge; }
        }
        $effective->{_prereqs}{prereqs}{$feature} = \@kept;
    }
    delete $effective->{_prereqs}{cpanmeta};
    my $expected = { %$original, edges => \@expected };
    die "carton-purifier: native binding changed unbound semantics\n"
        unless $json->encode(model($effective)) eq $json->encode($expected);
    die "carton-purifier: native binding mutated authored semantics\n"
        unless $json->encode(model($file)) eq $json->encode($original);
    return { file => $effective, originalModel => $original, effectiveModel => $expected, bindings => \@bindings };
}

sub save_verified {
    my ($bound, $destination) = @_;
    # These variables must be set before the Perl process starts for deterministic
    # native hash iteration. Do not claim changing them now controls Perl's seed.
    die "carton-purifier: deterministic native serializer environment required\n"
        unless ($ENV{PERL_HASH_SEED} // '') eq '0' && ($ENV{PERL_PERTURB_KEYS} // '') eq '0';
    $bound->{file}->save($destination);
    my $reparsed = Module::CPANfile->load($destination);
    die "carton-purifier: native serializer loses residual cpanfile semantics\n"
        unless $json->encode(model($reparsed)) eq $json->encode($bound->{effectiveModel});
    return $reparsed;
}

1;
