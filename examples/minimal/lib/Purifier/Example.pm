package Purifier::Example;
use strict;
use warnings;
use JSON::MaybeXS;
our $VERSION='0.01';
sub answer { 42 }
sub serialized { JSON::MaybeXS::encode_json({answer=>answer()}) }
1;
