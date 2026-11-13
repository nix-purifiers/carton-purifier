# SPDX-License-Identifier: MIT
# A distinct native profile; legacy scope-sdk.py and its SDK stay unchanged.
{ perlPackages, python3 }:
perlPackages.Carton.overrideAttrs (old: {
  nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ python3 ];
  postPatch = (old.postPatch or "") + "\n" + ''
    ${python3}/bin/python3 ${./scope-produced-sdk.py} "$PWD"
  '';
})
