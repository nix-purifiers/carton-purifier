# SPDX-License-Identifier: MIT
# A caller-owned native MakeMaker producer, including an unversioned class
# declared in its real module file rather than an invented loader alias.
{ pkgs, purifier }:
let
  inherit (pkgs) lib perl;
  source = pkgs.runCommand "owned-perl-projection-source" { } ''
    mkdir -p "$out/lib/Owned"
    cat > "$out/Makefile.PL" <<'PL'
    use ExtUtils::MakeMaker;
    WriteMakefile(NAME=>'Owned::Projection',VERSION_FROM=>'lib/Owned/Projection.pm');
    PL
    cat > "$out/lib/Owned/Projection.pm" <<'PL'
    package Owned::Projection;
    use strict;use warnings;
    our $VERSION='0.01';
    sub answer {42}
    package Owned::Projection::Unversioned;
    sub answer {43}
    1;
    PL
  '';
  sdk = import ../pkgs/build-carton-project/perl-library-sdk.nix { inherit lib purifier; } perl;
  tools = builtins.path {
    path = ../carton_purifier;
    name = "owned-perl-projection-observer";
    filter = path: type: baseNameOf path != "__pycache__" && !(lib.hasSuffix ".pyc" path);
  };
  request = sdk // {
    sourcePath = toString source;
    sourceIdentity = purifier.inputIdentity source;
    roots = [ "lib/perl5" ];
    sourceRoots."lib/perl5" = "lib";
    dependencies = [ ];
    allowedRoots = sdk.allowedRoots ++ [ (toString source) ];
  };
  producer = pkgs.runCommand "owned-native-perl-projection" {
    outputs = [ "out" "proof" ];
    nativeBuildInputs = [ perl pkgs.gnumake pkgs.python3 ];
    requestJSON = builtins.toJSON request;
    passAsFile = [ "requestJSON" ];
  } ''
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME" "$out" "$proof" work
    cp -R ${source}/. work/
    chmod -R u+w work
    cd work
    perl Makefile.PL INSTALL_BASE="$out"
    make
    make install
    cp MYMETA.json "$proof/MYMETA.json"
    ${pkgs.python3}/bin/python3 -B - "$requestJSONPath" "$out" "$proof" ${tools} <<'PY'
    import json,sys
    from pathlib import Path
    sys.path.insert(0,sys.argv[4])
    from perl_library import observe,canonical
    request=json.loads(Path(sys.argv[1]).read_text())
    request.update(producerPath=sys.argv[2],nativeMetadataPaths=[sys.argv[3]+'/MYMETA.json'])
    request['allowedRoots'] += [sys.argv[2],sys.argv[3]]
    Path(sys.argv[3]+'/observation.json').write_bytes(canonical(observe(request))+b'\n')
    PY
  '';
  projection = (pkgs.callPackage ../pkgs/build-carton-project/project-perl-library.nix { inherit purifier; }) {
    inherit producer source;
    roots = [ "lib/perl5" ];
    sourceRoots."lib/perl5" = "lib";
    observation = "${producer.proof}/observation.json";
  };
in
producer.overrideAttrs (old: { passthru = (old.passthru or { }) // { projections.perl = projection; }; })
