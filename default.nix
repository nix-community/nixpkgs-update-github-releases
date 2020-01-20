{ pkgs ? import <nixpkgs> {} }:

with pkgs;
rec {
  inherit pkgs;

  interpreter = python3.withPackages (p: with p;
    [requests dateutil libversion cachecontrol lockfile]
  );
}
