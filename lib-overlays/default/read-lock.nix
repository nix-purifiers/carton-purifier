# SPDX-License-Identifier: MIT
{ lib }:
{
  src,
  lockFile ? src + "/carton-purifier.lock.json",
  snapshot ? src + "/cpanfile.snapshot",
}:
let
  exists = builtins.pathExists lockFile && builtins.pathExists snapshot;
  raw = if exists then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  relative =
    s:
    builtins.isString s
    && s != ""
    && !(lib.hasPrefix "/" s)
    && !(builtins.elem ".." (lib.splitString "/" s));
  sri = s: builtins.isString s && builtins.match "sha256-[A-Za-z0-9+/]{43}=" s != null;
  authorPath =
    s:
    relative s && builtins.match "[A-Za-z0-9]/[A-Za-z0-9]{2}/[A-Za-z0-9_-]+/[A-Za-z0-9_.+-]+" s != null;
  inputs = data.inputs or { };
  inputsOK =
    builtins.isAttrs inputs
    && inputs ? cpanfile
    && builtins.all (
      name:
      relative name
      && builtins.isAttrs inputs.${name}
      && builtins.isString (inputs.${name}.content or null)
      && builtins.pathExists (src + "/${name}")
      && builtins.hashFile "sha256" (src + "/${name}") == (inputs.${name}.sha256 or null)
      && builtins.hashString "sha256" inputs.${name}.content == inputs.${name}.sha256
    ) (builtins.attrNames inputs);
  snapshotText = if exists then builtins.readFile snapshot else "";
  nativePaths = lib.concatMap (
    line:
    let
      value = builtins.match "    pathname: (.+)" line;
    in
    lib.optional (value != null) (builtins.head value)
  ) (lib.splitString "\n" snapshotText);
  distributions = data.distributions or [ ];
  entries = data.entries or [ ];
  distributionOK =
    d:
    builtins.isAttrs d
    && builtins.isString (d.name or null)
    && authorPath (d.pathname or null)
    && builtins.isAttrs (d.provides or null)
    && builtins.all (
      provided: builtins.isAttrs provided && builtins.isString (provided.version or null)
    ) (builtins.attrValues d.provides)
    && builtins.isAttrs (d.requirements or null)
    && builtins.all (value: builtins.isString value) (builtins.attrValues d.requirements);
  entryOK =
    e:
    builtins.isAttrs e
    && builtins.isString (e.path or null)
    && lib.hasPrefix "authors/id/" e.path
    && authorPath (lib.removePrefix "authors/id/" e.path)
    && sri (e.hash or null)
    && (e.url or null) == "https://cpan.metacpan.org/${e.path}"
    && (e.mirrors or null) == [ "https://backpan.perl.org/${e.path}" ]
    && !(e ? git);
  valid =
    exists
    && (data.schemaVersion or null) == 1
    && (data.purifier or null) == "carton"
    && inputsOK
    && lib.hasPrefix "# carton snapshot format: version 1.0\nDISTRIBUTIONS\n" snapshotText
    && builtins.isList distributions
    && builtins.all distributionOK distributions
    && builtins.isList entries
    && builtins.all entryOK entries
    && builtins.length (lib.unique (map (e: e.path) entries)) == builtins.length entries
    && builtins.length (lib.unique (map (d: d.pathname) distributions)) == builtins.length distributions
    && builtins.length distributions == builtins.length entries
    &&
      builtins.sort builtins.lessThan nativePaths
      == builtins.sort builtins.lessThan (map (d: d.pathname) distributions)
    && builtins.all (d: builtins.any (e: e.path == "authors/id/${d.pathname}") entries) distributions
    && builtins.isAttrs (data.snapshot or null)
    && builtins.hashFile "sha256" snapshot == (data.snapshot.sha256 or null)
    && builtins.isAttrs (data.toolVersions or null)
    && (data.toolVersions.carton or null) == "1.0.35"
    && (data.toolVersions.perl or null) == "5.42.3"
    && builtins.isString (data.toolVersions.gcc or null)
    && builtins.isString (data.toolVersions.sdk or null)
    && builtins.match "[0-9a-f]{64}" data.toolVersions.sdk != null;
in
{
  purifier = "carton";
  inherit entries data;
  nativeSnapshot = snapshotText;
  problems = lib.optional (
    !valid
  ) "Carton lock is missing, stale, or unsupported; run carton-purifier lock";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}
