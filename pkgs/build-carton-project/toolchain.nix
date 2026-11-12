# SPDX-License-Identifier: MIT
{
  symlinkJoin,
  makeWrapper,
  perl,
  nativeCarton,
  perlPackages,
  gcc,
  libxcrypt,
  lib,
  gnumake,
  gnutar,
  gzip,
  bzip2,
  xz,
  unzip,
  git,
  pkg-config,
  curl,
  cacert,
}:
symlinkJoin {
  name = "carton-purifier-toolchain";
  paths = [
    perl
    nativeCarton
    perlPackages.PodPerldoc
    gcc
    gnumake
    gnutar
    gzip
    bzip2
    xz
    unzip
    git
    pkg-config
    curl
    cacert
  ];
  nativeBuildInputs = [ makeWrapper ];
  postBuild = ''
    for tool in cc gcc c++ g++; do
      rm "$out/bin/$tool"
      makeWrapper ${gcc}/bin/$tool "$out/bin/$tool" \
        --add-flags '-isystem ${lib.getDev libxcrypt}/include -L${lib.getLib libxcrypt}/lib -Wl,-rpath,${lib.getLib libxcrypt}/lib'
    done
  '';
}
