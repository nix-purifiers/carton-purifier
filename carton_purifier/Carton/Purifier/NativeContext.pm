# SPDX-License-Identifier: MIT
package Carton::Purifier::NativeContext;
use strict;
use warnings;
use JSON::PP;
use Digest::SHA;
use CPAN::Meta::Requirements;
use Carton::Purifier::CPANfile;
use Carton::CPANfile;

my $profile;
my $json = JSON::PP->new->canonical->utf8;

sub install {
    $profile = $_[0];
    my $native = Carton::CPANfile->can('_build_requirements');
    no warnings 'redefine';
    *Carton::CPANfile::_build_requirements = sub {
        my ($file) = @_;
        my $path = $ENV{CARTON_PURIFIER_ROOT_BINDING};
        return $native->(@_) unless $path && -f $path;
        my $bound = read_json($path);
        die "carton-purifier: native root model differs from recorded binding\n"
            unless $json->encode(Carton::Purifier::CPANfile::model($file->_cpanfile))
                eq $json->encode($bound->{originalModel});
        my $selection = $bound->{selection};
        my $prereqs = $file->_cpanfile->prereqs_with(@{$selection->{selectedFeatures}});
        my $requirements = $prereqs->merged_requirements($selection->{wantedPhases}, $selection->{installTypes});
        $requirements->clear_requirement('perl');
        return $requirements;
    };
}

sub read_json {
    open my $file, '<', $_[0] or die "carton-purifier: open native context input: $!";
    binmode $file;
    return $json->decode(do { local $/; <$file> });
}

sub sha_file {
    open my $file, '<', $_[0] or die "carton-purifier: open native origin: $!";
    binmode $file;
    return Digest::SHA->new(256)->addfile($file)->hexdigest;
}

sub write_json {
    my ($path, $value, $append) = @_;
    open my $file, $append ? '>>' : '>', $path or die "carton-purifier: write native context: $!";
    binmode $file;
    print {$file} $json->encode($value), "\n";
    close $file or die "carton-purifier: close native context: $!";
}

sub features {
    my ($dist, $selected) = @_;
    $dist->{carton_purifier_features} = [@$selected];
}

sub bind_root {
    my ($cli, $dist, $selected) = @_;
    die "carton-purifier: root cpanfile outside native depth zero\n" unless $dist->{depth} == 0;
    features($dist, $selected);
    my %providers = map {
        my $row = $profile->{providers}{$_};
        die "carton-purifier: root provider lacks original input identity\n"
            unless ref($row->{providerIdentity}) eq 'HASH';
        ($_ => {%$row, providerIdentity => $row->{providerIdentity}{hash}})
    } keys %{$profile->{providers}};
    my $selection = {selectedFeatures => [@$selected], wantedPhases => [@{$dist->{want_phases}}],
                     installTypes => [@{$cli->{install_types}}]};
    my $bound = Carton::Purifier::CPANfile::bind($dist->{cpanfile}, \%providers, $selection);
    my $effective = $bound->{file};
    if (my $path = $ENV{CARTON_PURIFIER_EFFECTIVE_CPANFILE}) {
        $effective = Carton::Purifier::CPANfile::save_verified($bound, $path);
    }
    $dist->{cpanfile} = $effective;
    $cli->{cpanfile_global} = $effective;
    if (my $path = $ENV{CARTON_PURIFIER_ROOT_BINDING}) {
        write_json($path, {originalModel => $bound->{originalModel}, effectiveModel => $bound->{effectiveModel},
                          bindings => $bound->{bindings}, selection => $selection}, 0);
    }
}

sub record {
    my ($cli, $dist, $depth, $stage, $phases, $selected, $deps) = @_;
    my $destination = $ENV{CARTON_PURIFIER_NATIVE_CONTEXT} or return;
    my $identity;
    if ($depth == 0 && $dist->{source} eq 'local') {
        my $root = read_json($ENV{CARTON_PURIFIER_ROOT_IDENTITY});
        die "carton-purifier: malformed original root input record\n"
            unless ref($root) eq 'HASH' && join(',', sort keys %$root) eq 'input,sha256'
                && ($root->{sha256} // '') =~ /\A[0-9a-f]{64}\z/
                && ref($root->{input}) eq 'HASH' && join(',', sort keys %{$root->{input}}) eq 'context,hash'
                && ref($root->{input}{context}) eq 'HASH' && keys %{$root->{input}{context}}
                && ($root->{input}{hash} // '') eq Digest::SHA::sha256_hex($json->encode($root->{input}{context}));
        die "carton-purifier: authored root bytes differ from original input\n"
            unless sha_file($cli->{cpanfile_path}) eq $root->{sha256};
        $identity = {kind => 'root', input => $root->{input}};
    } elsif ($dist->{source} eq 'cpan' && $dist->{pathname} && $dist->{local_path}) {
        $identity = {kind => 'cpan', pathname => $dist->{pathname}, archiveSha256 => sha_file($dist->{local_path})};
    } else {
        die "carton-purifier: native invocation has no verified root/CPAN archive origin\n";
    }
    die "carton-purifier: unsupported native install types\n"
        unless $json->encode($cli->{install_types}) eq '["requires"]';
    my $requirements = CPAN::Meta::Requirements->new;
    for my $dep (@$deps) {
        die "carton-purifier: unexpected native dependency type\n" unless $dep->is_requirement;
        $requirements->add_string_requirement($dep->module, $dep->version || '0');
    }
    write_json($destination, {distIdentity => $identity, depth => 0 + $depth, stage => $stage,
        selectedFeatures => [@$selected], wantedPhases => [@$phases], installTypes => [@{$cli->{install_types}}],
        requirements => $requirements->as_string_hash}, 1);
}

1;
