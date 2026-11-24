# SPDX-License-Identifier: MIT
# A distinct native profile; legacy scope-sdk.py and its SDK stay unchanged.
{ perlPackages, python3 }:
let
  menlo = import ./produced-menlo.nix { inherit perlPackages python3; };
in
perlPackages.toPerlModule (perlPackages.Carton.overrideAttrs (old: {
  propagatedBuildInputs = map (
    input: if input.drvPath == perlPackages.MenloLegacy.drvPath then menlo else input
  ) old.propagatedBuildInputs;
  nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ python3 ];
  postPatch = (old.postPatch or "") + "\n" + ''
    ${python3}/bin/python3 ${./scope-produced-sdk.py} "$PWD"
  '';
}))
