# SPDX-License-Identifier: MIT
{ lib, runCommand, python3, writeText, fetchgit, runtimeShell, purifier }:
{ lock, profile, fetchers ? { }, nativeBuildInputs ? [ ] }:
let
  checked = purifier.checkLock lock;
  sources = purifier.tree ({
    name = "locked-produced-cpan-sources";
    entries = checked.entries;
    inherit runCommand fetchgit python3 writeText;
  } // fetchers);
  manifest = writeText "carton-produced-capture.json" (builtins.toJSON checked.data);
  snapshot = writeText "cpanfile.snapshot" checked.nativeSnapshot;
  tools = runCommand "carton-produced-environment-tools" { } ''
    mkdir "$out"
    cp -r ${profile.tools} "$out/carton_purifier"
  '';
in
runCommand "purified-carton-produced-environment" {
  nativeBuildInputs = [ python3 ] ++ nativeBuildInputs;
  spec = builtins.toJSON {
    inherit manifest snapshot sources runtimeShell;
    profile = toString profile;
    inherit (checked) rootIdentity;
  };
  passAsFile = [ "spec" ];
  passthru = { inherit profile; };
} ''
  PYTHONPATH=${tools} ${python3}/bin/python3 -B -m carton_purifier.build_produced "$specPath" "$out"
''
