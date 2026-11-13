# SPDX-License-Identifier: MIT
{ lib, system }:
references:
map (reference:
  let
    parts = lib.splitString "#" reference;
    source = builtins.head parts;
    flake = builtins.getFlake source;
    attribute = if builtins.length parts == 1 then "default" else builtins.elemAt parts 1;
    names = lib.splitString "." attribute;
    candidates = [ names ([ "packages" system ] ++ names) ([ "legacyPackages" system ] ++ names) ];
    present = builtins.filter (path: lib.hasAttrByPath path flake) candidates;
  in
  assert lib.assertMsg (builtins.length parts <= 2 && source != "" && attribute != "") "Invalid Perl dependency installable";
  if present == [ ] then throw "No Perl dependency output ${attribute} in ${source}"
  else lib.getAttrFromPath (builtins.head present) flake
) references
