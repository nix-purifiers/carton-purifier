# SPDX-License-Identifier: MIT
# Instantiated by the owning CLI with its original Nixpkgs/Core inputs.
{ manifest }:
let
  lib = import (@nixpkgs@ + "/lib");
  purifier = import (@purifier@ + "/nix/lib") { inherit lib; };
  source = builtins.toFile "carton-authored-inputs.json" (builtins.readFile manifest);
in
{
  path = source;
  input = purifier.inputIdentity source;
}
