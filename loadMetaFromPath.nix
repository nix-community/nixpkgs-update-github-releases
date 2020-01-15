# Not perfect, but it works™️
{ path ? null, url ? null }:

assert path == null || url == null;
assert path != null || url != null;

let
  path' = if url == null then path else (builtins.fetchTarball url);
  deepSeqId = x: builtins.deepSeq x x;
  pkgs = import path' {};
  versions = pkgs.lib.mapAttrs (
    name: value:
      let
        result = builtins.tryEval (
          deepSeqId (
            assert (value.version or null) != null;
            assert (value.meta.homepage or null) != null;
            assert pkgs.lib.isString value.version;
            assert pkgs.lib.isString value.meta.homepage;
            {
              inherit (value) version;
              inherit (value.meta) homepage;
            }
          )
        );
      in
        if result.success then result.value else null
    )
    pkgs;
  filtered = pkgs.lib.filterAttrs (_name: x: x != null) versions;
in
  filtered
