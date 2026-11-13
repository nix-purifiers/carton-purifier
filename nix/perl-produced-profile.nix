# SPDX-License-Identifier: MIT
{ lib, runCommand, python3, perl, purifier }:
{ dependencies, applicationPerl ? perl }:
let
  sdk = import ./perl-library-sdk.nix { inherit lib purifier; } applicationPerl;
  suppliers = import ./perl-library-inputs.nix { inherit lib purifier; } dependencies;
  tools = builtins.path {
    path = ../carton_purifier;
    name = "carton-produced-profile-tools";
    filter = path: type: !(builtins.elem (baseNameOf path) [ "__pycache__" ]) && !(lib.hasSuffix ".pyc" path);
  };
  declaration = sdk // { inherit suppliers; };
in
runCommand "carton-verified-produced-profile" {
  requestJSON = builtins.toJSON declaration;
  passAsFile = [ "requestJSON" ];
  passthru = { inherit declaration tools; };
} ''
  mkdir "$out"
  ${python3}/bin/python3 -B ${tools}/perl_profile.py "$requestJSONPath" "$out/profile.json"
''
