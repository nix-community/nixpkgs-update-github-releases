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
            let
              version =
                value.version or
                null;
              homepage =
                value.src.meta.homepage or
                value.meta.homepage or
                null;
            in
            assert pkgs.lib.isString version;
            assert pkgs.lib.isString homepage;
            {
              inherit version homepage;
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
