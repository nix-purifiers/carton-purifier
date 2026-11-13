# SPDX-License-Identifier: MIT
{ lib, runCommand, python3, runtimeShell, perl, purifier }:
{
  producer,
  source,
  roots,
  sourceRoots,
  observation,
  dependencies ? [ ],
  applicationPerl ? perl,
}:
let
  tools = builtins.path {
    path = ../../carton_purifier;
    name = "carton-perl-library-projector";
    filter = path: type: type == "directory" || builtins.any (name: lib.hasSuffix ("/" + name) path) toolNames;
  };
  toolNames = [
    "perl_projector.py"
    "perl_library.py"
    "perl_capture_context.py"
    "perl_sdk_inventory.py"
    "maker_mapping.py"
    "inspect-perl-library.pl"
    "Carton/Purifier/MakeMaker.pm"
  ];
  projectorIdentity = builtins.hashString "sha256" (
    builtins.toJSON (map (name: { inherit name; sha256 = builtins.hashFile "sha256" (../../carton_purifier + "/${name}"); }) toolNames)
  );
  sdk = import ./perl-library-sdk.nix { inherit lib purifier; } applicationPerl;
  outputs = import ./perl-producer-outputs.nix { inherit lib purifier; } producer;
  suppliers = import ./perl-library-inputs.nix { inherit lib purifier; } dependencies;
  supplierInputs = supplier:
    supplier.declared.runtimeInputPaths
    ++ [ { path = supplier.declared.sourcePath; identity = supplier.declared.sourceIdentity; } ]
    ++ map (output: { inherit (output) path identity; }) supplier.declared.producerOutputs
    ++ lib.concatMap supplierInputs supplier.declared.suppliers;
  supplierRoots = supplier:
    map (root: "${supplier.declared.producerPath}/${root}") supplier.declared.roots
    ++ lib.concatMap supplierRoots supplier.declared.suppliers;
  declared = sdk // {
    inherit roots sourceRoots projectorIdentity runtimeShell suppliers;
    observation = toString observation;
    sourcePath = toString source;
    sourceIdentity = purifier.inputIdentity source;
    producerPath = toString producer;
    producerIdentity = purifier.inputIdentity producer;
    producerOutputs = outputs;
    dependencyRoots = lib.unique (lib.concatMap (item: item.declared.allowedRoots) suppliers);
    dependencyInputPaths = lib.unique (lib.concatMap supplierInputs suppliers);
    dependencyLibraryRoots = lib.unique (lib.concatMap supplierRoots suppliers);
    allowedRoots = lib.unique ([ (toString source) ] ++ map (item: item.path) outputs ++ sdk.allowedRoots ++ declared.dependencyRoots);
  };
in
assert lib.assertMsg (lib.isDerivation producer) "Carton library producer must be an original derivation";
runCommand "carton-perl-installed-library" {
  nativeBuildInputs = [ python3 ];
  requestJSON = builtins.toJSON declared;
  passAsFile = [ "requestJSON" ];
  passthru = {
    perlLibraryDeclaration = declared;
    originalProducer = producer;
  };
} ''
  ${python3}/bin/python3 -B ${tools}/perl_projector.py "$requestJSONPath" "$out"
''
