# SPDX-License-Identifier: MIT
{
  lib,
  stdenvNoCC,
  makeWrapper,
  python3,
  nix,
  gh,
  toolchain,
  nativeCarton,
  perlnavigator,
  metadataPerl,
  perl,
  gcc,
  sdkVersion,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
stdenvNoCC.mkDerivation {
  pname = "carton-purifier";
  version = "0.1.0";
  src = ../.;
  nativeBuildInputs = [ makeWrapper ];
  dontBuild = true;
  installPhase = ''
    mkdir -p "$out/bin" "$out/lib/carton-purifier"
    cp -r carton_purifier nix "$out/lib/carton-purifier/"
    install -m755 bin/carton-purifier "$out/bin/carton-purifier"
    substituteInPlace "$out/lib/carton-purifier/nix/realize.nix" \
      --replace-fail '@nixpkgs@' '${nixpkgsSrc}' \
      --replace-fail '@purifier@' '${purifierSrc}'
    wrapProgram "$out/bin/carton-purifier" \
      --prefix PATH : ${
        lib.makeBinPath [
          python3
          nix
          gh
          toolchain
        ]
      } \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set CARTON_PURIFIER_CARTON ${nativeCarton}/bin/carton \
      --set CARTON_PURIFIER_PERL ${perl}/bin/perl \
      --set CARTON_PURIFIER_PROVE ${perl}/bin/prove \
      --set CARTON_PURIFIER_PERLNAVIGATOR ${perlnavigator}/bin/perlnavigator \
      --set CARTON_PURIFIER_METADATA_PERL ${metadataPerl}/bin/perl \
      --set CARTON_PURIFIER_GCC_VERSION ${gcc.version} \
      --set CARTON_PURIFIER_SDK_VERSION ${sdkVersion} \
      --set CARTON_PURIFIER_SDK "$out" \
      --set CARTON_PURIFIER_WRAPPER_BIN "$out/bin"
    for tool in carton perl prove perlnavigator; do
      makeWrapper "$out/bin/carton-purifier" "$out/bin/$tool" --add-flags "--native --tool=$tool --"
    done
    for program in ${toolchain}/bin/*; do
      name=$(basename "$program")
      if [ ! -e "$out/bin/$name" ]; then ln -s "$program" "$out/bin/$name"; fi
    done
  '';
  meta = {
    description = "Native Carton workflow with locked Nix-resolved CPAN dependencies";
    homepage = "https://nix-purifiers.github.io/";
    license = lib.licenses.mit;
    platforms = [
      "x86_64-linux"
      "aarch64-linux"
    ];
    mainProgram = "carton-purifier";
  };
}
