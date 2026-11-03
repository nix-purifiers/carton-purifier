use strict;
use ExtUtils::MakeMaker;
WriteMakefile(NAME=>'Purifier::Example',VERSION_FROM=>'lib/Purifier/Example.pm',EXE_FILES=>['bin/example'],PREREQ_PM=>{'JSON::MaybeXS'=>'1.004008','Cpanel::JSON::XS'=>'4.38'},TEST_REQUIRES=>{'Test::Fatal'=>'0.017'});
