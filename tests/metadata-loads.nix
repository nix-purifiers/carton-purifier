# SPDX-License-Identifier: MIT
# Native MakeMaker fixtures load a real selected-SDK module/object only while
# Module::Metadata evaluates VERSION, without explicit native probes.
{ pkgs, purifier }:
let
 core=purifier;
 perl=pkgs.perl.withPackages(ps:[ps.BitVector ps.ClassAccessor]);
 sdk=import ../pkgs/build-carton-project/perl-library-sdk.nix {inherit(pkgs)lib;inherit purifier;} perl;
 tools=builtins.path {path=../carton_purifier;name="native-metadata-phase-tools";filter=path: type: baseNameOf path != "__pycache__" && !(pkgs.lib.hasSuffix ".pyc" path);};
 foreign=pkgs.runCommand "same-byte-foreign-native-sdk-files" {nativeBuildInputs=[perl];} ''
  mkdir -p "$out"
  ${perl}/bin/perl -MBit::Vector -MDynaLoader -MFile::Copy -MJSON::PP -MDigest::SHA -e '
   my ($object)=grep { m{/Vector\.(?:so|bundle|dylib)$} } @DynaLoader::dl_shared_objects;
   die "native BitVector object absent" unless defined $object;
   File::Copy::copy($object,"$ENV{out}/native.so") or die $!;
   File::Copy::copy($INC{"Bit/Vector.pm"},"$ENV{out}/native.pm") or die $!;
   sub sha {open my $f,"<",$_[0] or die $!;binmode $f;Digest::SHA->new(256)->addfile($f)->hexdigest}
   die "copy differs" unless sha($object) eq sha("$ENV{out}/native.so") && sha($INC{"Bit/Vector.pm"}) eq sha("$ENV{out}/native.pm");
   open my $f,">","$ENV{out}/origins.json" or die $!;
   print {$f} JSON::PP->new->canonical->encode({module=>$INC{"Bit/Vector.pm"},object=>$object,moduleSha256=>sha($INC{"Bit/Vector.pm"}),objectSha256=>sha($object),nativeVersion=>$Bit::Vector::VERSION});'
 '';
 make = kind:
 let
  source=pkgs.runCommand "owned-metadata-phase-source-${kind}" {nativeBuildInputs=[perl];} ''
   mkdir -p "$out/lib/Owned"
   ${perl}/bin/perl -MJSON::PP - ${foreign}/origins.json "$out/lib/Owned/Metadata.pm" ${pkgs.lib.escapeShellArg kind} ${foreign} <<'PL'
   use strict;use warnings;
   my ($origins,$target,$kind,$foreign)=@ARGV;
   open my $f,'<',$origins or die $!;my $sdk=JSON::PP->new->decode(do{local $/;<$f>});
   my $body;
   if ($kind =~ /module$/) {
    $body=$kind eq 'owned-module' ? 'require Bit::Vector;' : 'require '.JSON::PP->new->encode("$foreign/native.pm").';';
   } else {
    my $object=$kind eq 'owned-object' ? $sdk->{object} : "$foreign/native.so";
    my $quoted=JSON::PP->new->encode($object);
    $body='require DynaLoader; my $object='.$quoted.'; my $handle=DynaLoader::dl_load_file($object,0) or die DynaLoader::dl_error(); my $symbol=DynaLoader::dl_find_symbol($handle,"boot_Bit__Vector") or die "missing original native boot symbol"; push @DynaLoader::dl_shared_objects,$object; if ($ENV{METADATA_CONTROL_EVENTS}) {open my $event,">>",$ENV{METADATA_CONTROL_EVENTS} or die $!;print {$event} "loaded:$object:boot-present\\n";close $event;}';
   }
   open my $out,'>',$target or die $!;
   print {$out} "package Owned::Metadata;\nuse strict;use warnings;\nour \$VERSION = do { $body '0.01' };\n1;\n";
   PL
   cat > "$out/Makefile.PL" <<'PL'
   use ExtUtils::MakeMaker;
   WriteMakefile(NAME=>'Owned::Metadata',VERSION_FROM=>'lib/Owned/Metadata.pm');
   PL
  '';
  request=sdk//{sourcePath=toString source;sourceIdentity=core.inputIdentity source;roots=["lib/perl5"];sourceRoots={"lib/perl5"="lib";};dependencies=[];allowedRoots=sdk.allowedRoots++[(toString source)];};
 in pkgs.runCommand "native-metadata-phase-control-${kind}" {
  outputs=["out" "proof"];nativeBuildInputs=[perl pkgs.gnumake pkgs.python3];
  requestJSON=builtins.toJSON request;passAsFile=["requestJSON"];
 } ''
  export HOME="$TMPDIR/home" METADATA_CONTROL_EVENTS="$proof/native-object-events.txt"
  mkdir -p "$HOME" "$out" "$proof" work
  cp -R ${source}/. work/
  chmod -R u+w work
  cd work
  ${perl}/bin/perl Makefile.PL INSTALL_BASE="$out"
  make
  make install
  cp MYMETA.json "$proof/MYMETA.json"
  ${pkgs.python3}/bin/python3 -B - "$requestJSONPath" "$out" "$proof" ${tools} ${tools} ${pkgs.lib.escapeShellArg kind} ${foreign}/origins.json <<'PY'
  import json,subprocess,sys
  from pathlib import Path
  request=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);proof=Path(sys.argv[3]);kind=sys.argv[6]
  request.update(producerPath=str(out),nativeMetadataPaths=[str(proof/'MYMETA.json')]);request['allowedRoots'] += [str(out),str(proof)]
  (proof/'request.json').write_text(json.dumps(request,sort_keys=True)+'\n')
  sys.path.insert(0,sys.argv[4]);from perl_library import observe,verify,canonical
  import copy
  expected_foreign=kind.startswith('foreign-')
  try:
   current=observe(request)
  except ValueError as exc:
   assert expected_foreign and 'escapes declared closure' in str(exc),(kind,str(exc))
   result={'kind':kind,'refused':str(exc)}
  else:
   assert not expected_foreign,kind
   assert current['xsLoads']==[] and not any(x['module']=='Bit/Vector.pm' for x in current['sdk']['moduleOrigins'])
   original=json.loads(Path(sys.argv[7]).read_text());expected=str(Path(original['module'] if kind.endswith('module') else original['object']).resolve(strict=True))
   records=current['metadataLoads']['modules'] if kind.endswith('module') else current['metadataLoads']['sharedObjects']
   key='file' if kind.endswith('module') else 'path';assert any(x[key]==expected and x['input']['kind']=='input' for x in records),records
   replay=[]
   if kind=='owned-module':
    altered=copy.deepcopy(current);row=next(x for x in altered['metadataLoads']['modules'] if x['file']==expected)
    base=next(x['identity'] for x in request['runtimeInputPaths'] if Path(current['sdk']['baseExecutable']).is_relative_to(Path(x['path']).resolve(strict=True)))
    row['input']={'kind':'input','identity':base}
    try: verify(request,altered)
    except ValueError as exc: assert 'stale production observation: metadataLoads' in str(exc);replay.append(str(exc))
    else: raise AssertionError('foreign original owner accepted')
   else:
    altered=copy.deepcopy(current);altered['metadataLoads']['sharedObjects']=[x for x in altered['metadataLoads']['sharedObjects'] if x['path']!=expected]
    try: verify(request,altered)
    except ValueError as exc: assert 'stale production observation: metadataLoads' in str(exc);replay.append(str(exc))
    else: raise AssertionError('missing metadata-only native object accepted')
   (proof/'replay-refusals.json').write_text(json.dumps(replay)+'\n')
   (proof/'observation.json').write_bytes(canonical(current)+b'\n')
   result={'kind':kind,'xsProbes':[],'baselineExcludesMetadataOnlyBitVector':True,'metadataLoads':current['metadataLoads']}
  (proof/'result.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
  PY
 '';
in pkgs.runCommand "perl-metadata-native-load-controls" {nativeBuildInputs=[pkgs.python3];} ''
 mkdir -p "$out"
 cp ${(make "owned-module").proof}/result.json "$out/owned-module.json"
 cp ${(make "foreign-module").proof}/result.json "$out/foreign-module.json"
 cp ${(make "owned-object").proof}/result.json "$out/owned-object.json"
 cp ${(make "foreign-object").proof}/result.json "$out/foreign-object.json"
 cp ${(make "owned-module").proof}/replay-refusals.json "$out/owner-replay.json"
 cp ${(make "owned-object").proof}/replay-refusals.json "$out/object-replay.json"
'' 
