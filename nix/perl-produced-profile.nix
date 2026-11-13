# SPDX-License-Identifier: MIT
{ lib, runCommand, python3, perl, perlPackages, gcc, symlinkJoin, makeWrapper, gnumake, gnutar, gzip, bzip2, xz, coreutils, unzip, curl, cacert, runtimeShell, purifier }:
{ dependencies, applicationPerl ? perl }:
let
  sdk = import ./perl-library-sdk.nix { inherit lib purifier; } applicationPerl;
  suppliers = import ./perl-library-inputs.nix { inherit lib purifier; } dependencies;
  nativeCarton = import ./produced-carton.nix { inherit perlPackages python3; };
  toolPerl = perl.withPackages (_: [ nativeCarton ]);
  compiler = import ./perl-native-compiler.nix { inherit lib symlinkJoin makeWrapper gcc; } applicationPerl;
  tools = builtins.path {
    path = ../carton_purifier;
    name = "carton-produced-profile-tools";
    filter = path: type: !(builtins.elem (baseNameOf path) [ "__pycache__" ]) && !(lib.hasSuffix ".pyc" path);
  };
  declaration = sdk // {
    inherit suppliers runtimeShell;
    toolsPath = toString tools;
    toolsIdentity = purifier.inputIdentity tools;
    toolSdk = import ./perl-library-sdk.nix { inherit lib purifier; } toolPerl;
    nativePath = lib.makeBinPath [ compiler gnumake gnutar gzip bzip2 xz coreutils unzip curl ];
    sslCertFile = "${cacert}/etc/ssl/certs/ca-bundle.crt";
    nativeTools = {
      carton = purifier.inputIdentity nativeCarton;
      programs = map (input: { path = toString input; identity = purifier.inputIdentity input; }) [ compiler gnumake gnutar gzip bzip2 xz coreutils unzip curl ];
      certificates = { path = toString cacert; identity = purifier.inputIdentity cacert; };
      adapters = purifier.inputIdentity (builtins.path {
        path = ./.;
        name = "carton-produced-profile-adapters";
        filter = path: type: baseNameOf path != "__pycache__" && !(lib.hasSuffix ".pyc" path);
      });
    };
    toolVersions = { carton = nativeCarton.version; perl = (applicationPerl.perl or applicationPerl).version; gcc = gcc.version; };
  };
in
runCommand "carton-verified-produced-profile" {
  requestJSON = builtins.toJSON declaration;
  passAsFile = [ "requestJSON" ];
  passthru = { inherit declaration tools; };
} ''
  mkdir "$out"
  cp "$requestJSONPath" "$out/declaration.json"
  ${python3}/bin/python3 -B ${tools}/perl_profile.py "$requestJSONPath" "$out/profile.json"
''
