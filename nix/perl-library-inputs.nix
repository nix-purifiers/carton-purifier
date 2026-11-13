# SPDX-License-Identifier: MIT
{ lib, purifier }:
dependencies:
map (
  input:
  let
    repository = input.repository;
    declared = repository.perlLibraryDeclaration;
  in
  assert lib.assertMsg (lib.isDerivation repository && repository ? perlLibraryDeclaration) "Carton Perl dependencies require an owning installed-library projection";
  assert lib.assertMsg (input.identity == declared.producerIdentity) "Carton Perl projection belongs to a different original producer";
  {
    inherit declared;
    observation = declared.observation;
    catalog = "${repository}/catalog.json";
    loader = "${repository}/bin/perl";
  }
) (purifier.projectInputs { inherit dependencies; formats = [ "perl" ]; })
