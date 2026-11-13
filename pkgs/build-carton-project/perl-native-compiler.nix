# SPDX-License-Identifier: MIT
# Keep the selected compiler and the real native dependencies of its Perl SDK.
{ lib, symlinkJoin, makeWrapper, gcc }:
applicationPerl:
let
  base = applicationPerl.perl or applicationPerl;
  dependencies = base.propagatedBuildInputs or [ ];
  flags = lib.concatMapStringsSep " " (
    input: "-isystem ${lib.getDev input}/include -L${lib.getLib input}/lib -Wl,-rpath,${lib.getLib input}/lib"
  ) dependencies;
in
assert lib.assertMsg (builtins.all lib.isDerivation dependencies) "Carton requires original native Perl SDK dependency inputs";
symlinkJoin {
  name = "carton-perl-native-compiler";
  paths = [ gcc ];
  nativeBuildInputs = [ makeWrapper ];
  postBuild = ''
    for tool in cc gcc c++ g++; do
      rm "$out/bin/$tool"
      makeWrapper ${gcc}/bin/$tool "$out/bin/$tool" --add-flags ${lib.escapeShellArg flags}
    done
  '';
}
