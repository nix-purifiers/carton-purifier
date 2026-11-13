# SPDX-License-Identifier: MIT
use strict;
use warnings;
use JSON::PP;
use Carton::Purifier::ProducedProfile;

my $profile_path = shift @ARGV;
open my $file, '<', $profile_path or die "carton-purifier: open verified profile: $!";
my $profile = JSON::PP->new->decode(do { local $/; <$file> });
die "carton-purifier: unsupported produced profile\n"
    unless $profile->{format} eq 'carton-produced-profile-v1';
Carton::Purifier::ProducedProfile::install($profile);
require Carton::CLI;
exit Carton::CLI->new->run(@ARGV);
