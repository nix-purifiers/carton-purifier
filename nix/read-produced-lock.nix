# SPDX-License-Identifier: MIT
# Read authored source/lock files only. Supplier catalogs remain build inputs.
{ lib, purifier }:
{ src, lockFile ? src + "/carton-purifier.lock.json", snapshot ? src + "/cpanfile.snapshot" }:
let
  exact = value: names: builtins.isAttrs value && builtins.attrNames value == builtins.sort builtins.lessThan names;
  sha = value: builtins.isString value && builtins.match "[0-9a-f]{64}" value != null;
  text = builtins.isString;
  strings = value: builtins.isList value && builtins.all text value;
  nullableText = value: value == null || text value;
  relative = value: text value && value != "" && !(lib.hasPrefix "/" value)
    && builtins.all (part: part != "" && part != "." && part != "..") (lib.splitString "/" value);
  author = value: text value && builtins.match "[A-Za-z0-9]/[A-Za-z0-9]{2}/[A-Za-z0-9_-]+/[A-Za-z0-9_.+-]+" value != null;
  identity = value: exact value [ "context" "hash" ] && builtins.isAttrs value.context
    && value.context != { } && sha value.hash && value.hash == builtins.hashString "sha256" (builtins.toJSON value.context);
  declared = value: exact value [ "root" "path" ] && relative value.root && relative value.path;
  edge = value: exact value [ "feature" "phase" "type" "module" "constraint" "options" ]
    && text value.feature && builtins.elem value.phase [ "runtime" "configure" "build" "test" "develop" ]
    && builtins.elem value.type [ "requires" "recommends" "suggests" "conflicts" ]
    && text value.module && text value.constraint && builtins.isAttrs value.options;
  model = value: exact value [ "mirrors" "features" "edges" ] && strings value.mirrors
    && builtins.isAttrs value.features && builtins.all (item: exact item [ "description" ] && text item.description) (builtins.attrValues value.features)
    && builtins.isList value.edges && builtins.all edge value.edges;
  provided = value: exact value [ "input" "semanticIdentity" "catalogSha256" ]
    && identity value.input && sha value.semanticIdentity && sha value.catalogSha256;
  sdk = value: exact value [ "applicationPerl" "executable" "baseExecutable" "config" "runtimeInputs" "inc" "moduleOrigins" ]
    && identity value.applicationPerl && text value.executable && text value.baseExecutable
    && builtins.isAttrs value.config && builtins.all nullableText (builtins.attrValues value.config)
    && builtins.isList value.runtimeInputs && builtins.all identity value.runtimeInputs && strings value.inc
    && builtins.isList value.moduleOrigins && builtins.all (item:
      exact item [ "module" "file" "sha256" "input" ] && text item.module && text item.file && sha item.sha256 && identity item.input
    ) value.moduleOrigins;
  exists = builtins.pathExists lockFile && builtins.pathExists snapshot;
  raw = if exists then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  inputs = data.inputs or { };
  inputsOK = builtins.isAttrs inputs && inputs ? cpanfile && builtins.all (name:
    relative name && exact inputs.${name} [ "content" "sha256" ] && text inputs.${name}.content && sha inputs.${name}.sha256
    && builtins.pathExists (src + "/${name}")
    && builtins.hashFile "sha256" (src + "/${name}") == inputs.${name}.sha256
    && builtins.hashString "sha256" inputs.${name}.content == inputs.${name}.sha256
  ) (builtins.attrNames inputs);
  authoredSource = if inputsOK then builtins.toFile "carton-authored-inputs.json" (builtins.toJSON inputs + "\n") else null;
  rootIdentity = if authoredSource == null then null else purifier.inputIdentity authoredSource;
  distributions = data.distributions or [ ];
  entries = data.entries or [ ];
  distribution = value: exact value [ "name" "pathname" "provides" "requirements" ] && text value.name && author value.pathname
    && builtins.isAttrs value.provides && builtins.all (item: exact item [ "version" ] && text item.version) (builtins.attrValues value.provides)
    && builtins.isAttrs value.requirements && builtins.all text (builtins.attrValues value.requirements);
  entry = value: exact value [ "path" "url" "hash" "mirrors" ]
    && text value.path && lib.hasPrefix "authors/id/" value.path && author (lib.removePrefix "authors/id/" value.path)
    && text value.hash && builtins.match "sha256-[A-Za-z0-9+/]{43}=" value.hash != null
    && value.url == "https://cpan.metacpan.org/${value.path}"
    && value.mirrors == [ "https://backpan.perl.org/${value.path}" ];
  snapshotText = if exists then builtins.readFile snapshot else "";
  snapshotPaths = lib.concatMap (line: let match = builtins.match "    pathname: (.+)" line;
    in lib.optional (match != null) (builtins.head match)) (lib.splitString "\n" snapshotText);
  invocation = value:
    exact value [ "distIdentity" "depth" "stage" "selectedFeatures" "wantedPhases" "installTypes" "requirements" ]
    && builtins.isInt value.depth && value.depth >= 0 && builtins.elem value.stage [ "configure" "post-configure" ]
    && strings value.selectedFeatures && strings value.wantedPhases && value.installTypes == [ "requires" ]
    && builtins.isAttrs value.requirements && builtins.all text (builtins.attrValues value.requirements)
    && (if (value.distIdentity.kind or null) == "root" then
      exact value.distIdentity [ "kind" "input" ] && value.depth == 0 && value.distIdentity.input == rootIdentity
    else (value.distIdentity.kind or null) == "cpan"
      && exact value.distIdentity [ "kind" "pathname" "archiveSha256" ] && value.depth > 0
      && author value.distIdentity.pathname && sha value.distIdentity.archiveSha256
      && builtins.any (item: item.path == "authors/id/${value.distIdentity.pathname}"
        && builtins.convertHash { hash = item.hash; toHashFormat = "base16"; } == value.distIdentity.archiveSha256) entries);
  context = data.nativeContext or { };
  contextOK = exact context [ "format" "profileIdentity" "applicationSdk" "without" "originalModel" "effectiveModel"
    "effectiveCpanfile" "effectiveCpanfileSha256" "bindings" "providedGraphIdentity" "nativeSnapshotSha256"
    "nativeInstalledGraphSha256" "nativeInvocations" ]
    && context.format == "carton-produced-context-v1" && sha context.profileIdentity && sdk context.applicationSdk
    && strings context.without && model context.originalModel && model context.effectiveModel
    && text context.effectiveCpanfile && sha context.effectiveCpanfileSha256
    && builtins.hashString "sha256" context.effectiveCpanfile == context.effectiveCpanfileSha256
    && builtins.isList context.bindings && builtins.all (item:
      exact item [ "edge" "providerIdentity" "package" "nativeVersion" "declaredIn" "action" ]
      && edge item.edge && sha item.providerIdentity && text item.package && nullableText item.nativeVersion
      && builtins.isList item.declaredIn && builtins.all declared item.declaredIn
      && builtins.elem item.action [ "requires-removed" "conflict-checked" ]
    ) context.bindings
    && context.providedGraphIdentity == builtins.hashString "sha256" (builtins.toJSON data.provided)
    && context.nativeSnapshotSha256 == data.snapshot.sha256
    && context.nativeInstalledGraphSha256 == builtins.hashString "sha256" (builtins.toJSON distributions)
    && builtins.isList context.nativeInvocations && builtins.all invocation context.nativeInvocations
    && builtins.sort builtins.lessThan (map (item: item.stage)
      (builtins.filter (item: item.distIdentity.kind == "root") context.nativeInvocations)) == [ "configure" "post-configure" ];
  valid = exists && exact data [ "schemaVersion" "purifier" "inputs" "snapshot" "distributions" "entries" "toolVersions" "provided" "nativeContext" ]
    && builtins.isInt data.schemaVersion && data.schemaVersion == 2 && data.purifier == "carton" && inputsOK
    && exact data.snapshot [ "sha256" ] && sha data.snapshot.sha256 && builtins.hashString "sha256" snapshotText == data.snapshot.sha256
    && lib.hasPrefix "# carton snapshot format: version 1.0\nDISTRIBUTIONS\n" snapshotText
    && builtins.isList distributions && builtins.all distribution distributions && builtins.isList entries && builtins.all entry entries
    && builtins.length entries == builtins.length distributions
    && builtins.length (lib.unique (map (item: item.path) entries)) == builtins.length entries
    && builtins.sort builtins.lessThan snapshotPaths == builtins.sort builtins.lessThan (map (item: item.pathname) distributions)
    && builtins.all (item: builtins.any (archive: archive.path == "authors/id/${item.pathname}") entries) distributions
    && builtins.isList data.provided && builtins.all provided data.provided
    && builtins.length (lib.unique (map (item: item.input.hash) data.provided)) == builtins.length data.provided
    && exact data.toolVersions [ "carton" "perl" "gcc" "sdk" ] && builtins.all text (builtins.attrValues data.toolVersions)
    && sha data.toolVersions.sdk && contextOK && data.toolVersions.sdk == context.profileIdentity;
in {
  purifier = "carton";
  inherit data entries authoredSource rootIdentity;
  nativeSnapshot = snapshotText;
  problems = lib.optional (!valid) "Carton produced lock is missing, stale, or unsupported; recapture the native dependency context";
  outputs = { packages = [ "default" "environment" "project" ]; tests = [ "default" ]; release = [ "default" ]; };
}
