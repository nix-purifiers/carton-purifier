# SPDX-License-Identifier: MIT
{
  project,
  companion,
  snapshot,
  target ? "environment",
}:
let
  nixpkgsSrc = /. + "@nixpkgs@";
  pkgs = import nixpkgsSrc { };
  purifier = import (/. + "@purifier@/nix/lib") { inherit (pkgs) lib; };
  nativeCarton = pkgs.callPackage ./carton.nix { };
  toolchain = pkgs.callPackage ./toolchain.nix { inherit nativeCarton; };
  metadataPerl = pkgs.perl.withPackages (_: [ nativeCarton ]);
  sdkVersion = import ./sdk-version.nix { inherit nixpkgsSrc; };
  args = {
    src = /. + project;
    lockFile = /. + companion;
    snapshot = /. + snapshot;
  };
  lock = import ../../lib-overlays/default/read-lock.nix { inherit (pkgs) lib; } args;
in
if target == "environment" then
  pkgs.callPackage ./environment.nix {
    inherit
      purifier
      nativeCarton
      toolchain
      metadataPerl
      sdkVersion
      ;
  } { inherit lock; }
else if target == "release" then
  (pkgs.callPackage ./default.nix {
    inherit
      purifier
      nativeCarton
      toolchain
      metadataPerl
      sdkVersion
      ;
  } args).release
else
  throw "carton-purifier: unknown target"
