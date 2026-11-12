# SPDX-License-Identifier: MIT
{
  lib,
  runCommand,
  fetchgit,
  python3,
  writeText,
  purifier,
  nativeCarton,
  toolchain,
  metadataPerl,
  perl,
  gcc,
  sdkVersion,
  cacert,
  makeWrapper,
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/carton-purifier.lock.json",
  snapshot ? src + "/cpanfile.snapshot",
  fetchers ? { },
  nativeBuildInputs ? [ ],
  doCheck ? true,
  buildCommand ? ''
    if [ -f Makefile.PL ]; then
      perl Makefile.PL INSTALL_BASE="$out"
      make
    elif [ -f Build.PL ]; then
      perl Build.PL --install_base "$out"
      perl Build
    else
      echo "Provide buildCommand for this Perl project" >&2
      exit 1
    fi
  '',
  checkCommand ? "if [ -f Makefile ]; then make test; else perl Build test; fi",
  installCommand ? "if [ -f Makefile ]; then make install; else perl Build install; fi",
  srcFilter ?
    path: type:
    !(builtins.elem (baseNameOf path) [
      ".git"
      ".carton-purifier"
      "local"
      "blib"
      "Makefile"
      "Build"
      "pm_to_blib"
      "result"
      "__pycache__"
    ])
    && !(
      baseNameOf path == "vendor"
      && type == "directory"
      && builtins.all (
        name:
        builtins.elem name [
          "cache"
          "bin"
        ]
      ) (builtins.attrNames (builtins.readDir path))
    )
    && !(lib.hasSuffix "/vendor/cache" (toString path))
    && !(lib.hasSuffix "/vendor/bin" (toString path))
    && !(lib.hasPrefix "MYMETA." (baseNameOf path))
    && !(lib.hasSuffix ".log" (baseNameOf path)),
}:
let
  lock = purifier.checkLock (
    import ../../lib-overlays/default/read-lock.nix { inherit lib; } { inherit src lockFile snapshot; }
  );
  environment = import ./environment.nix {
    inherit
      lib
      runCommand
      fetchgit
      python3
      writeText
      purifier
      nativeCarton
      toolchain
      metadataPerl
      perl
      gcc
      sdkVersion
      cacert
      ;
  } { inherit lock fetchers nativeBuildInputs; };
  source = lib.cleanSourceWith {
    inherit src;
    filter = srcFilter;
  };
  project =
    runCommand "purified-perl-project"
      {
        nativeBuildInputs = [
          toolchain
          python3
          makeWrapper
        ]
        ++ nativeBuildInputs;
      }
      ''
        export PATH=${toolchain}/bin:$PATH
        export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=1
        mkdir -p "$HOME" work "$out"
        cp -pr ${source}/. work/
        chmod -R u+w work
        cd work
        export PERL5LIB=${environment}/local/lib/perl5
        export PERL_CARTON_PATH=${environment}/local PERL_CARTON_CPANFILE="$PWD/cpanfile"
        export CARTON_PURIFIER_SNAPSHOT=${environment}/cpanfile.snapshot CARTON_PURIFIER_FROZEN=1
        ${buildCommand}
        ${lib.optionalString doCheck checkCommand}
        ${installCommand}
        python3 ${../../carton_purifier/normalize.py} "$out" "$out/lib/perl5"
        if [ -d "$out/bin" ]; then
          HOST_PATH=${perl}/bin:$HOST_PATH patchShebangs --host --update "$out/bin"
          for program in "$out/bin"/*; do
            if [ -f "$program" ] && [ -x "$program" ]; then
              wrapProgram "$program" --set PERL5LIB "$out/lib/perl5:${environment}/local/lib/perl5" --unset PERL5OPT
            fi
          done
        fi
      '';
  release =
    runCommand "perl-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        set -o pipefail
        mkdir -p "$out" source
        cp -r ${source}/. source/
        chmod -R u+w source
        cp ${lockFile} source/carton-purifier.lock.json
        cp ${snapshot} source/cpanfile.snapshot
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - source | gzip -n > "$out/source.tar.gz"
      '';
in
assert lock.problems == [ ];
assert lib.assertMsg (
  lock.data.toolVersions.sdk == sdkVersion
) "Carton SDK changed; run carton-purifier lock";
{
  packages = {
    default = project;
    inherit project environment;
  };
  tests = project;
  inherit release;
  fetches = lock.entries;
}
