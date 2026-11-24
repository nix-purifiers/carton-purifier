# SPDX-License-Identifier: MIT
package Carton::Dist::SDK;
use strict;
use warnings;
use CPAN::Meta::Requirements;

# An original Nix SDK is already selected as a whole. This node has no CPAN
# resolution edges; runtime_inputs retains its real Nix module environment.
# It does not describe an upstream CPAN distribution's prerequisites.
sub new {
    my ($class, %args) = @_;
    die "carton-purifier: original SDK identity required\n"
        unless ref($args{identity}) eq 'HASH' && ($args{identity}{hash} // '') =~ /\A[0-9a-f]{64}\z/;
    die "carton-purifier: original SDK closure and provides required\n"
        unless ref($args{runtimeInputs}) eq 'ARRAY' && @{$args{runtimeInputs}} && ref($args{provides}) eq 'HASH';
    return bless {name => 'sdk:' . $args{identity}{hash}, identity => $args{identity},
                  runtime_inputs => $args{runtimeInputs}, provides => $args{provides},
                  requirements => CPAN::Meta::Requirements->new}, $class;
}
sub name { $_[0]{name} }
sub identity { $_[0]{identity} }
sub runtime_inputs { $_[0]{runtime_inputs} }
sub provides { $_[0]{provides} }
sub requirements { $_[0]{requirements} }
sub is_core { 0 }
sub provides_module { exists $_[0]{provides}{$_[1]} }
sub version_for {
    my ($self, $module) = @_;
    die "carton-purifier: SDK package not declared: $module\n" unless $self->provides_module($module);
    return $self->{provides}{$module}{version};
}
1;
