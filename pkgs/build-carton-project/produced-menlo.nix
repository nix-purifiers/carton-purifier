# SPDX-License-Identifier: MIT
{ perlPackages, python3 }:
perlPackages.MenloLegacy.overrideAttrs (old: {
  nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ python3 ];
  postPatch = (old.postPatch or "") + "\n" + ''
    ${python3}/bin/python3 ${./scope-produced-menlo.py} "$PWD"
  '';
})
