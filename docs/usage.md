# Lua generator usage

`generator.py` generates NameProvider Lua data for Java and Bedrock Edition. Requires Python 3.10+ and only its standard library. Output is compatible with Lua 5.1. Automatic mode downloads Java Edition data; manual mode accepts local language JSON files for either edition.

## Global options

| Option | Default | Description |
| --- | --- | --- |
| `-h, --help` | — | Show help and exit. After a subcommand, show that mode's help. |
| `-e, --encoding ENCODING` | Auto-detect | Decode language JSON with the selected encoding, such as `gb18030`. |
| `-o, --output OUTPUT` | `-` (STDOUT) | Write UTF-8 to a file, or to STDOUT with `-`. A value is required when the option is present. |
| `-b, --blocked-strings KEYS` | None | Comma-separated exact keys whose later columns must use the first input's value. |
| `-B, --blocked-strings-file FILE` | None | Read one blocked key per line from a file; `-` reads STDIN. |

Global options can appear before or after the subcommand. Running without a subcommand only shows help and does not download data or create files.

## Automatic mode

```text
python3 generator.py [GLOBAL_OPTIONS] auto [OPTIONS] [LANGUAGE ...]
```

Download language data for Java Edition 1.13+. Generating output requires at least one language code; there are no default languages. Every requested language must exist in the selected version. The output includes version and asset comments and `_meta.version`.

### Mode options

| Option | Default | Description |
| --- | --- | --- |
| `-l, --list-versions` | Off | List version IDs, types and release times in aligned columns. No languages are required; only the manifest is read. |
| `-v, --version VERSION` | `latest` | Select a version ID or one of the selectors below. |
| `--manifest SOURCE` | `https://piston-meta.mojang.com/mc/game/version_manifest.json` | Read a manifest from an HTTP(S) URL or local JSON file. |
| `--assets-base SOURCE` | `https://resources.download.minecraft.net/` | Read language objects from an HTTP(S) base URL or local directory. |
| `--timeout SECONDS` | `30` | Set a positive, finite timeout for each network operation. |

### Version selectors

| Value | Selection |
| --- | --- |
| Version ID, such as `1.21.8` | The matching manifest entry. |
| `latest` | The first manifest entry; it may be a snapshot. |
| `latest-release` | The manifest's latest release. |
| `latest-snapshot` | The manifest's latest snapshot. |

## Manual mode

```text
python3 generator.py [GLOBAL_OPTIONS] manual [OPTIONS] JSON [JSON ...]
```

Read one or more local language JSON files for Java or Bedrock Edition. Bedrock `.lang` files can first be converted with [`lang2json.py`](lang2json.md). Filenames and language codes have no special meaning, and input files are retained. Values are serialized as supplied; the generator does not adapt format markers.

### Mode options

| Option | Default | Description |
| --- | --- | --- |
| `-v, --version VERSION` | Omitted | Write the literal value to `_meta.version` and the `-- version:` comment. |
| `--version-note TEXT` | Omitted | Add a parenthesized annotation to the version comment; requires `--version`. It does not change `_meta.version`. |
| `--asset TEXT` | Omitted | Write asset source text to the `-- asset:` comment. |
| `--asset-note TEXT` | Omitted | Add a parenthesized annotation, such as a timestamp, to the asset comment; requires `--asset`. |

Metadata is optional and must be single-line text. Its format follows [Module:NameProvider/snapshot](https://zh.minecraft.wiki/w/Module:NameProvider/snapshot?action=raw).

## Data rules

| Rule | Behavior |
| --- | --- |
| Column order | Follow the order of language codes in `auto`, or file paths in `manual`. |
| Keys | Use only the first input's keys. Keys found only in later inputs are excluded. |
| Fallback | A missing translation uses the first input's value for that key. |
| First input | Any language can be first; English is optional. |
| Row order | Compare dot-separated key segments from left to right with natural ordering; compare the next segment when the current segments are equal. |

Digit runs within each segment compare by numeric value: `item.test2` precedes `item.test10`. A key precedes its children when all shared segments are equal: `a.b` precedes `a.b.c`, which precedes `a.ba`. Dots separate segments; for example, the order is `3d_export.include`, `3d_export.include_players`, `3d_export.off`. Zero-padded numeric runs with equal values continue to the next segment; if every segment compares equally, the complete key breaks the tie by byte order. Keys and values themselves are retained exactly.

## Encoding and output

Language JSON is decoded strictly. UTF-8, UTF-16 and UTF-32, with or without BOM, are detected automatically. `--encoding` applies only to language data; manifests, version metadata and asset indexes detect their own JSON encoding. JSON Unicode escapes and surrogate pairs are decoded without normalization; unpaired surrogates are rejected.

Output uses UTF-8 without BOM and LF line endings, including when the terminal uses another encoding. Strings are escaped for Lua 5.1, with decimal escapes for control characters that have no short escape. JSON-only `\uXXXX` escapes become actual characters. Use `-o FILE` to write a file or `-o -` for STDOUT.

## Sources and downloads

Version metadata, asset indexes and clients follow the locations in the manifest and its linked metadata. Relative locations resolve against the referring URL or file.

Language objects use `<first two hash characters>/<full hash>` under `--assets-base`. A local manifest and object directory can supply an entirely offline download tree.

The client archive is downloaded only when `en_us` is requested. It is read in a temporary directory that is removed afterward.

## Blocked strings

The comma-separated and file sources can be combined; duplicate keys are removed. Matching keys keep their first-input value in every later column. Unmatched keys are ignored. Case, whitespace and Unicode are preserved for exact matching.

Key files and STDIN accept UTF-8 with an optional BOM, or BOM-marked UTF-16/32, independently of `--encoding`. LF and CRLF line endings are supported. Blank lines and empty comma-separated entries are ignored.

Matched names are sorted by key name in a comment after the metadata and before `return {`:

```lua
--[[
BLOCKED STRINGS
	entity.minecraft.frostbite
	item.minecraft.frostbite_spawn_egg
]]
```

No block comment is added when no keys match. Version listing does not read blocked-list files or STDIN.

## Examples

### Versions and language order

```sh
python3 generator.py auto en_us zh_cn zh_tw zh_hk
python3 generator.py auto -v 1.21.8 en_us lzh
python3 generator.py auto -v latest-release en_us lzh
python3 generator.py auto -l
python3 generator.py auto got_de zlm_arab kn_in en_us
```

### Custom sources

```sh
python3 generator.py auto --manifest https://example.org/version_manifest.json en_us lzh
python3 generator.py auto --manifest ./version_manifest.json -v 1.21.8 en_us lzh
python3 generator.py auto --manifest ./offline/manifest.json --assets-base ./offline/objects en_us lzh
```

### Manual data and metadata

```sh
python3 generator.py manual en_us.json lzh.json
python3 generator.py -e gb18030 manual English.json Chinese.json
python3 generator.py -o names.lua manual -v 26.4-snapshot-3 \
    --version-note crowdin-approved+suggested-20261007T073914Z \
    --asset https://example.org/assets.json \
    --asset-note 2026-10-06T13:00:46+00:00 \
    en_us.json zh_cn.json zh_tw.json zh_hk.json
```

### Bedrock language files

Convert each language's `.lang` data into JSON, then use manual mode:

```sh
python3 lang2json.py -t -o en_US.json texts/en_US.lang
python3 lang2json.py -t -o zh_CN.json texts/zh_CN.lang
python3 lang2json.py -t -o zh_TW.json texts/zh_TW.lang
python3 generator.py -o names.lua manual en_US.json zh_CN.json zh_TW.json
```

See [converter usage](lang2json.md) for merging multiple files and format character preparation.

### Blocked lists

```sh
python3 generator.py -b entity.minecraft.frostbite,item.minecraft.frostbite_spawn_egg auto en_us zh_cn zh_tw zh_hk
python3 generator.py -B blocked.txt manual en_us.json zh_cn.json zh_tw.json zh_hk.json
python3 generator.py -B - manual en_us.json zh_cn.json zh_tw.json zh_hk.json
```

### Global option placement

```sh
python3 generator.py -o names.lua auto en_us lzh
python3 generator.py auto -o names.lua en_us lzh
```
