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
}:
{
  lock,
  fetchers ? { },
  nativeBuildInputs ? [ ],
}:
let
  checked = purifier.checkLock lock;
  sources = purifier.tree (
    {
      name = "locked-cpan-sources";
      entries = checked.entries;
      inherit
        runCommand
        fetchgit
        python3
        writeText
        ;
    }
    // fetchers
  );
  manifest = writeText "carton-capture.json" (builtins.toJSON checked.data);
  snapshot = writeText "cpanfile.snapshot" checked.nativeSnapshot;
in
assert lib.assertMsg (
  checked.data.toolVersions.perl == perl.version
  && checked.data.toolVersions.carton == nativeCarton.version
  && checked.data.toolVersions.gcc == gcc.version
  && checked.data.toolVersions.sdk == sdkVersion
) "Carton SDK changed; run carton-purifier lock";
runCommand "purified-carton-environment"
  {
    nativeBuildInputs = [
      toolchain
      python3
    ]
    ++ nativeBuildInputs;
  }
  ''
      export PATH=${toolchain}/bin:$PATH
      mkdir -p "$out/local/lib/perl5" "$out/vendor/cache/authors/id" "$TMPDIR/home" work
      export HOME="$TMPDIR/home" PERL_CPANM_HOME="$TMPDIR/cpanm"
      export PERL_CARTON_PATH="$out/local" PERL_CARTON_MIRROR="file://$out/vendor/cache"
      export SSL_CERT_FILE=${cacert}/etc/ssl/certs/ca-bundle.crt
      python3 ${../../carton_purifier/build.py} ${manifest} ${snapshot} ${sources} "$PWD/work" "$out" ${metadataPerl}/bin/perl ${../../carton_purifier/snapshot.pl}
      cd work
      carton install --deployment --cached || { tail -c 9000 "$PERL_CPANM_HOME"/work/*/build.log; exit 1; }
      ${metadataPerl}/bin/perl ${../../carton_purifier/snapshot.pl} ${snapshot} "$out/local" "$PWD/cpanfile" > "$TMPDIR/actual.json"
    python3 ${../../carton_purifier/check-installed.py} ${manifest} "$TMPDIR/actual.json"
    python3 ${../../carton_purifier/normalize.py} "$out"
      cp ${snapshot} "$out/cpanfile.snapshot"
      cp ${manifest} "$out/capture.json"
      ln -s ${sources} "$out/sources"
  ''
