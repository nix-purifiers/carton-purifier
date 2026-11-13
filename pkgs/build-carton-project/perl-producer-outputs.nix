# SPDX-License-Identifier: MIT
# Output ownership comes from the original producer derivation, never from a
# captured pathname, the observation's dirname, or an arbitrary passthru path.
{ lib, purifier }:
producer:
let
  names = producer.outputs or [ ];
  output = name: builtins.getAttr name producer;
  valid =
    lib.isDerivation producer
    && builtins.isList names
    && names != [ ]
    && builtins.length (lib.unique names) == builtins.length names
    && builtins.all (
      name:
      builtins.isString name
      && builtins.hasAttr name producer
      && lib.isDerivation (output name)
      && (output name).drvPath == producer.drvPath
      && (output name).outputName == name
    ) names;
in
assert lib.assertMsg valid "Carton Perl provenance requires original output derivations of the declared producer";
map (name: {
  inherit name;
  path = toString (output name);
  identity = purifier.inputIdentity (output name);
}) names
