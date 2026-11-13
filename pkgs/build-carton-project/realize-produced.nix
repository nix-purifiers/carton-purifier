# SPDX-License-Identifier: MIT
{ references, project, companion ? "", snapshot ? "", target ? "profile" }:
let
  pkgs = import (/. + "@nixpkgs@") { };
  purifier = import (/. + "@purifier@/nix/lib") { inherit (pkgs) lib; };
  dependencies = import ./resolve-dependencies.nix { inherit (pkgs) lib; system = pkgs.stdenv.hostPlatform.system; } (builtins.fromJSON references);
  profile = (pkgs.callPackage ./dependency-profile.nix { inherit purifier; }) {
    inherit dependencies;
    ownerDeclaration = builtins.storePath "@profile@/declaration.json";
    tools = builtins.storePath "@tools@";
  };
  lock = purifier.checkLock (import ./read-produced-lock.nix { inherit (pkgs) lib; inherit purifier; } {
    src = /. + project;
    lockFile = /. + companion;
    snapshot = /. + snapshot;
  });
  environment = (pkgs.callPackage ./produced-environment.nix { inherit purifier; }) { inherit lock profile; };
  source = pkgs.lib.cleanSourceWith {
    src = /. + project;
    filter = path: type:
      !(builtins.elem (baseNameOf path) [ ".git" ".carton-purifier" "local" "blib" "Makefile" "Build" "pm_to_blib" "result" "__pycache__" ])
      && !(baseNameOf path == "vendor" && type == "directory" && builtins.all (name: builtins.elem name [ "cache" "bin" ]) (builtins.attrNames (builtins.readDir path)))
      && !(pkgs.lib.hasSuffix "/vendor/cache" (toString path))
      && !(pkgs.lib.hasSuffix "/vendor/bin" (toString path))
      && !(pkgs.lib.hasPrefix "MYMETA." (baseNameOf path))
      && !(pkgs.lib.hasSuffix ".log" (baseNameOf path));
  };
  releaseLock = builtins.path { path = /. + companion; name = "carton-purifier.lock.json"; };
  releaseSnapshot = builtins.path { path = /. + snapshot; name = "cpanfile.snapshot"; };
  release = pkgs.runCommand "carton-produced-source-release" { nativeBuildInputs = [ pkgs.gnutar pkgs.gzip ]; } ''
    set -o pipefail
    ${environment}/bin/carton check
    mkdir -p "$out" source
    cp -r ${source}/. source/
    chmod -R u+w source
    cp ${releaseLock} source/carton-purifier.lock.json
    cp ${releaseSnapshot} source/cpanfile.snapshot
    tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - source | gzip -n > "$out/source.tar.gz"
  '';
in
if target == "profile" then profile
else if target == "environment" then environment
else if target == "release" then release
else throw "carton-purifier: unsupported produced target"
