# .lang converter usage

`lang2json.py` converts and merges Bedrock `.lang` files into one language JSON object. Requires Python 3.10+ and only its standard library.

```text
python3 lang2json.py [OPTIONS] FILE [FILE ...]
```

Running without arguments only shows help. Options can appear before, after or between input files.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `-h, --help` | — | Show help and exit. |
| `-e, --encoding ENCODING` | UTF-8 or BOM-marked UTF-16/32 | Override decoding for all input files, for example `gb18030`. Without this option, each file's BOM is handled separately. |
| `-o, --output OUTPUT` | `-` (STDOUT) | Write UTF-8 JSON to a file, or to STDOUT with `-`. A value is required when the option is present. |
| `-t, --translate-parser` | Off | Prepare original Bedrock values once for TranslateParser: adapt single-digit indices and integer markers, and escape literal percent signs. |
| `FILE ...` | Required | Read files from highest to lowest priority; the first file's value wins conflicts. `-` reads STDIN and can appear once. |

```sh
python3 lang2json.py -o en_US.json vanilla.lang extra.lang
python3 lang2json.py -e gb18030 -o language.json translated.lang
python3 lang2json.py -o language.json - < input.lang
```

## Parsing and merge rules

- The output contains the union of all input keys. Files are listed from highest to lowest priority: the first file containing a key supplies its value, and later files fill missing keys. An empty value still counts as present. Within each file, the last record for a key wins.
- Blank lines and whole-line `#` comments are skipped. Inline comments begin at `##` or a literal Tab followed by `#`; the first marker wins. Adjacent Tabs used to separate the comment are removed.
- The first `=` separates the key and value. Further `=`, single `#`, URLs, `//` and `/* */` text remain part of the value.
- Every value loses trailing ordinary spaces (U+0020) and no-break spaces (NBSP, U+00A0), including runs that mix the two. This applies with or without `-t`, after comment removal. Leading and interior whitespace, key names and other trailing characters are retained. A value containing only these spaces becomes an empty value and still takes precedence over later files.
- Input uses physical LF or CRLF lines. Unicode separators, combining characters, invisible characters and private-use characters are preserved, with no Unicode normalization. Only the initial encoding BOM is removed.
- Format markers such as `%d`, `%.2f`, `%1` and `§a` are preserved by default.

Invalid encoding, a missing `=`, an empty key or a missing file stops conversion. Malformed records report the file and physical line number. Every input is validated before output is written.

Output is a JSON object of string keys and values, encoded as UTF-8 without BOM with LF line endings. JSON escaping preserves quotes, backslashes and control characters. The terminal's encoding does not change the output encoding.

## Format characters

Without `-t`, all format characters remain as they appear in the input value. With `-t`, the script prepares the merged values for TranslateParser. Keys are unchanged, and conversion runs after file and record precedence is resolved.

The following tables describe the general conversion rules.

```sh
python3 lang2json.py -t -o en_US.json vanilla.lang extra.lang
```

### Parameters and literal suffixes

The script recognizes `%s`, `%d`, and indexed string or integer markers. A bare index consists of exactly one ASCII digit, `0` through `9`. Digits, letters, spaces and dollar signs following that digit are retained as literal suffixes unless they form a recognized `$s` or `$d` marker.

| Input text | JSON value for TranslateParser |
| --- | --- |
| `%s` | `%s` |
| `%d` | `%s` |
| `%1$s` | `%1$s` |
| `%1$d` | `%1$s` |
| `%1 / %2` | `%1$s / %2$s` |
| `%1%1` | `%1$s%1$s` |
| `%0` | `%0$s` |
| `%12` | `%1$s2` |
| `%02` | `%0$s2` |
| `%02d` | `%0$s2d` |
| `%03d` | `%0$s3d` |
| `%12$s` | `%12$s` |
| `%02$d` | `%02$d` |
| `%1s` | `%1$ss` |
| `%2d` | `%2$sd` |
| `%1$` | `%1$s$` |
| `%1$S` | `%1$s$S` |
| `%2$h` | `%2$s$h` |
| `%1$f` | `%1$s$f` |
| `%1 $s` | `%1$s $s` |
| `%1 X $d` | `%1$s X $d` |
| `%2$%d` | `%2$s$%s` |
| `%s / %2 / %1$d` | `%s / %2$s / %1$s` |

Existing multi-digit `%N$s` and `%N$d` forms are retained in full, including leading zeros. Single-digit `%N$d` becomes `%N$s`. Each marker keeps its original position and index; mixed implicit and indexed markers are not renumbered. The script does not substitute arguments, pad numbers or round floating-point values.

### Literal percent signs

Every literal `%` in the original value becomes `%%`. `%f`, `%.2f` and unknown non-numeric forms are literal text. In a run followed by a recognized parameter, the earlier percent signs are literal and the final marker is adapted normally.

| Input text | JSON value for TranslateParser |
| --- | --- |
| `%f` | `%%f` |
| `%.2f` | `%%.2f` |
| `%X` | `%%X` |
| `%` | `%%` |
| `%%` | `%%%%` |
| `%%%` | `%%%%%%` |
| `%%%%` | `%%%%%%%%` |
| `%%1` | `%%%1$s` |
| `%%s` | `%%%s` |
| `%%%s` | `%%%%%s` |
| `%%%%s` | `%%%%%%%s` |
| `%1%%` | `%1$s%%%%` |
| `100% accurate` | `100%% accurate` |
| `%1$s%` | `%1$s%%` |

Conversion scans each original value once. Apply `-t` once to the original `.lang` data; applying it again escapes literal percent signs again.

### URL encodings

Inside a URL with a `scheme://` prefix, a percent sign followed by two hexadecimal digits is treated as a literal URL encoding. Existing `%N$s` and `%N$d` markers are recognized before URL encodings. Outside a URL, the single-digit bare-index rule applies to forms such as `%28`.

| Input text | JSON value for TranslateParser |
| --- | --- |
| `https://example.test/%28name%29` | `https://example.test/%%28name%%29` |
| `https://example.test/?q=%E4%B8%AD` | `https://example.test/?q=%%E4%%B8%%AD` |
| `%28` outside a URL | `%2$s8` |

### Content retained

- Standalone `$s`, `$d`, `$f`, `$S`, `$h` and `$` are retained. Literal suffixes are not removed or corrected.
- Minecraft color and style codes such as `§a`, `§l` and `§r`, and special markers such as `@` and `&…&`, are retained.
- `-t` does not add backslash processing. Unicode characters and combining forms are preserved without normalization. Leading and interior whitespace, including NBSP, and other trailing characters such as Tabs, Unicode separators and invisible controls are retained; only trailing U+0020 and U+00A0 are removed.

## Example file order

Choose the input files and their order explicitly. List the base `vanilla` pack first, then `oreui`, followed by supplementary packs. Earlier files retain their values for duplicate keys; later files contribute keys that are still missing. This example creates one JSON for each language under a selected data directory:

```sh
bedrock_data='/path/to/minecraft/data'

for language in en_US zh_CN zh_TW; do
    python3 lang2json.py -t -o "$language.json" \
        "$bedrock_data/resource_packs/vanilla/texts/$language.lang" \
        "$bedrock_data/resource_packs/oreui/texts/$language.lang" \
        "$bedrock_data/resource_packs/chemistry/texts/$language.lang" || exit
done
```

Omit `-t` to keep format characters unchanged. Pass only files that exist for each language. The script uses the supplied order and does not discover packs or select their priority automatically. Put a selected override file before `vanilla` when its translations should take priority over the base pack.

## Generate Lua from JSON

Convert each language separately, then pass the resulting JSON files to manual mode in the desired column order:

```sh
python3 generator.py -o names.lua manual en_US.json zh_CN.json zh_TW.json
```

The first JSON supplies the output keys and fallback translations; any language can be first. Keys found only in later languages are excluded. See [manual mode options](usage.md#manual-mode) for metadata and blocked strings.
