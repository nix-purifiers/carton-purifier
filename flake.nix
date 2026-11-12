# SPDX-License-Identifier: MIT
{
  description = "Locked, Nix-resolved dependencies for Carton and Perl";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        carton-purifier = final.lib.makeScope final.newScope (scope: {
          nativeCarton = scope.callPackage ./pkgs/build-carton-project/carton.nix { };
          metadataPerl = final.perl.withPackages (_: [ scope.nativeCarton ]);
          toolchain = scope.callPackage ./pkgs/build-carton-project/toolchain.nix { };
          sdkVersion = import ./pkgs/build-carton-project/sdk-version.nix { nixpkgsSrc = nixpkgs; };
          cli = scope.callPackage ./pkgs/cli/default.nix {
            nixpkgsSrc = nixpkgs;
            purifierSrc = purifier;
          };
          buildCartonProject = scope.callPackage ./pkgs/build-carton-project/default.nix {
            purifier = import (purifier + "/nix/lib") { inherit (final) lib; };
          };
        });
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (system: {
        default = (pkgsFor system).carton-purifier.cli;
        cli = self.packages.${system}.default;
        native = (pkgsFor system).carton-purifier.nativeCarton;
        sdk = (pkgsFor system).carton-purifier.toolchain;
      });
      lib.carton-purifier = (nixpkgs.lib.extend (import ./lib-overlays/default)).carton-purifier;
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/carton-purifier";
          meta.description = "Lock and prefetch CPAN dependencies";
        };
      });
      checks = forAll (
        system:
        let
          build = (pkgsFor system).carton-purifier.buildCartonProject { src = ./examples/minimal; };
        in
        {
          environment = build.packages.environment;
          project = build.packages.default;
          release = build.release;
          cli = self.packages.${system}.default;
          installed = (pkgsFor system).runCommand "perl-installed-consumer" { } ''
            ${build.packages.default}/bin/example > output.json
            ${(pkgsFor system).python3}/bin/python3 -c 'import json; assert json.load(open("output.json")) == {"answer": 42}'
            mkdir "$out"
            cp output.json "$out/answer.json"
          '';
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}
