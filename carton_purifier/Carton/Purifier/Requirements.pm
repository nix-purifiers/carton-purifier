# SPDX-License-Identifier: MIT
package Carton::Purifier::Requirements;
use strict;
use warnings;
use CPAN::Meta::Requirements;
use CPAN::Meta::Check;

# The profile caller must already have validated the provider catalogs, payloads,
# application runtime and collision checks. This helper does not confer authority
# on arbitrary records or substitute filenames for packages declared in Types.pm.
sub unsatisfied {
    my ($providers, $search_inc, @deps) = @_;
    my $requirements = CPAN::Meta::Requirements->new;
    for my $dep (grep $_->is_requirement, @deps) {
        $requirements->add_string_requirement($dep->module => $dep->requires_version || '0');
    }
    my @failed;
    for my $module (sort $requirements->required_modules) {
        next unless exists $providers->{$module};
        my $provider = $providers->{$module};
        unless ($requirements->accepts_module($module, $provider->{nativeVersion})) {
            push @failed, 'provided package ' . $module . ' does not satisfy native requirement '
                . $requirements->requirements_for_module($module);
        }
        # A rejected provider remains a failure; it is never silently replaced by
        # a CPAN lookup. Every nonprovided requirement still reaches native Check.
        $requirements->clear_requirement($module);
    }
    my $native = CPAN::Meta::Check::check_requirements($requirements, 'requires', $search_inc);
    push @failed, grep defined, values %$native;
    return @failed;
}
1;
