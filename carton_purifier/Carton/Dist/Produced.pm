# SPDX-License-Identifier: MIT
package Carton::Dist::Produced;
use strict;
use warnings;
use CPAN::Meta::Requirements;

sub new {
    my ($class, %args) = @_;
    die "carton-purifier: missing produced identity\n"
        unless ($args{identity} // '') =~ /\A[0-9a-f]{64}\z/;
    die "carton-purifier: missing native provides/requirements\n"
        unless ref($args{provides}) eq 'HASH' && ref($args{requirements}) eq 'HASH';
    my $requirements = CPAN::Meta::Requirements->from_string_hash($args{requirements});
    return bless {
        name => 'provided:' . $args{identity},
        provides => $args{provides}, requirements => $requirements,
    }, $class;
}
sub name { $_[0]{name} }
sub provides { $_[0]{provides} }
sub requirements { $_[0]{requirements} }
sub is_core { 0 }
sub provides_module { exists $_[0]{provides}{$_[1]} }
sub version_for {
    my ($self, $module) = @_;
    die "carton-purifier: produced package not declared: $module\n" unless $self->provides_module($module);
    return $self->{provides}{$module}{version};
}
sub add_string_requirement { shift->requirements->add_string_requirement(@_) }
sub required_modules { shift->requirements->required_modules(@_) }
sub requirements_for_module { shift->requirements->requirements_for_module(@_) }
1;
