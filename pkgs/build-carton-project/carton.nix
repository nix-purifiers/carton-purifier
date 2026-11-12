# SPDX-License-Identifier: MIT
{ perlPackages, python3 }:
perlPackages.Carton.overrideAttrs (old: {
  nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ python3 ];
  postPatch =
    (old.postPatch or "")
    + "\n"
    + ''
      python3 ${./scope-sdk.py} "$PWD"
    '';
})
