# SPDX-License-Identifier: MIT
# Describe the real selected interpreter and its original module environment.
# This reads derivation attributes only; native Config and file inventories are
# observed inside the producer/projector builds.
{ lib, purifier }:
perl:
let
  base = perl.perl or perl;
  paths = perl.paths or [ ];
  inputs = lib.unique ([ perl base ] ++ paths);
  descriptor = input: {
    path = toString input;
    identity = purifier.inputIdentity input;
  };
in
assert lib.assertMsg (lib.isDerivation perl && lib.isDerivation base) "Carton Perl projection requires an immutable selected Perl SDK";
assert lib.assertMsg (builtins.isList paths && builtins.all lib.isDerivation paths) "Carton Perl SDK module environment must retain its original derivation inputs";
{
  applicationPerl = {
    executable = "${perl}/bin/perl";
    identity = purifier.inputIdentity perl;
  };
  basePerl = {
    executable = "${base}/bin/perl";
    identity = purifier.inputIdentity base;
  };
  runtimeInputs = map purifier.inputIdentity inputs;
  runtimeInputPaths = map descriptor inputs;
  allowedRoots = map toString inputs;
}
