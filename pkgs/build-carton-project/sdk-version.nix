# SPDX-License-Identifier: MIT
{ nixpkgsSrc }:
builtins.hashString "sha256" (
  builtins.toJSON {
    nixpkgs = toString nixpkgsSrc;
    scope = builtins.hashFile "sha256" ./scope-sdk.py;
    toolchain = builtins.hashFile "sha256" ./toolchain.nix;
  }
)
