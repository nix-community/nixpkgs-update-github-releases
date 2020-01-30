# Not perfect, but it works™️
{ path ? null, url ? null }:

assert path == null || url == null;
assert path != null || url != null;

let
  path' = if url == null then path else (builtins.fetchTarball url);
  deepSeqId = x: builtins.deepSeq x x;
  maybeToList = x: if x == null then [] else [x];
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
              pages =
                maybeToList (value.src.meta.homepage or null) ++
                value.src.urls or [] ++
                maybeToList (value.meta.homepage or null) ++
                [];
            in
            assert pkgs.lib.isString version;
            assert pkgs.lib.all pkgs.lib.isString pages;
            {
              inherit version pages;
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
