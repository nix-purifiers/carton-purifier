# SPDX-License-Identifier: MIT
{ lib, runCommand, python3, writeText, callPackage, purifier, perl, runtimeShell, makeWrapper, gnutar, gzip }:
{
  src,
  dependencies,
  without ? [ ],
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
  srcFilter,
}:
let
  lock = purifier.checkLock (import ./read-produced-lock.nix { inherit lib purifier; } { inherit src lockFile snapshot; });
  profile = (callPackage ./perl-produced-profile.nix { inherit purifier; }) {
    inherit dependencies;
    applicationPerl = perl;
  };
  environment = (callPackage ./produced-environment.nix { inherit purifier; }) {
    inherit lock profile fetchers nativeBuildInputs;
  };
  source = lib.cleanSourceWith { inherit src; filter = srcFilter; };
  releaseLock = builtins.path { path = lockFile; name = "carton-purifier.lock.json"; };
  releaseSnapshot = builtins.path { path = snapshot; name = "cpanfile.snapshot"; };
  commands = writeText "carton-produced-project-build.sh" (
    buildCommand + "\n" + lib.optionalString doCheck (checkCommand + "\n") + installCommand + "\n"
  );
  project = runCommand "purified-produced-perl-project" {
    nativeBuildInputs = [ python3 makeWrapper ] ++ nativeBuildInputs;
  } ''
    export PATH=${environment}/bin:${profile.declaration.nativePath}:$PATH
    export HOME="$TMPDIR/home" SOURCE_DATE_EPOCH=1
    mkdir -p "$HOME" work "$out"
    cp -pr ${source}/. work/
    chmod -R u+w work
    cd work
    ${environment}/bin/carton exec -- ${runtimeShell} -e ${commands}
    ${python3}/bin/python3 ${../carton_purifier/normalize.py} "$out" "$out/lib/perl5"
    perllib="$out/lib/perl5:$(${environment}/bin/perl -e 'print join q(:), @INC')"
    if [ -d "$out/bin" ]; then
      HOST_PATH=${perl}/bin:$HOST_PATH patchShebangs --host --update "$out/bin"
      for program in "$out/bin"/*; do
        if [ -f "$program" ] && [ -x "$program" ]; then
          wrapProgram "$program" --set PERL5LIB "$perllib" --prefix PATH : ${perl}/bin:${environment}/bin --unset PERL5OPT --unset PERLLIB
        fi
      done
    fi
  '';
  release = runCommand "produced-perl-project-release" { nativeBuildInputs = [ gnutar gzip ]; } ''
    set -o pipefail
    mkdir -p "$out" source
    cp -r ${source}/. source/
    chmod -R u+w source
    cp ${releaseLock} source/carton-purifier.lock.json
    cp ${releaseSnapshot} source/cpanfile.snapshot
    tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - source | gzip -n > "$out/source.tar.gz"
  '';
in
assert lock.problems == [ ];
assert lib.assertMsg (dependencies != [ ]) "Carton schema2 requires its original Nix dependencies";
assert lib.assertMsg (without == lock.data.nativeContext.without) "Carton native group selection changed; recapture the lock";
{
  packages = { default = project; inherit project environment; };
  tests = project;
  inherit release profile;
  fetches = lock.entries;
}
