# SPDX-License-Identifier: MIT
{ lib, runCommand, python3, purifier }:
{ ownerDeclaration, tools, dependencies }:
let
  suppliers = import ./perl-library-inputs.nix { inherit lib purifier; } dependencies;
in
runCommand "carton-owning-dependency-profile" {
  requestJSON = builtins.toJSON { inherit ownerDeclaration suppliers; };
  passAsFile = [ "requestJSON" ];
  passthru = { inherit tools; };
} ''
  mkdir "$out"
  ${python3}/bin/python3 -B ${tools}/perl_dependency_profile.py "$requestJSONPath" "$out"
''
