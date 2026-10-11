# NameProvider Data Generator

Generate Lua data for the [NameProvider module](https://zh.minecraft.wiki/w/Module:NameProvider).

## Lua generator

`generator.py` generates NameProvider data for Java and Bedrock Edition. Requires Python 3.10+ and only its standard library. Output is compatible with Lua 5.1.

```sh
python3 generator.py                              # show help
python3 generator.py auto en_us zh_cn zh_tw zh_hk  # latest version
python3 generator.py auto -v 1.21.8 en_us lzh       # specified version
python3 generator.py -o names.lua manual en_us.json lzh.json
```

`auto` downloads Java Edition language data. `manual` reads local language JSON files, including Bedrock files produced by the converter below.

Languages or files set the output column order. The first input supplies the keys and fallback translations. Rows use natural order within each dot-separated key segment. Output defaults to UTF-8 STDOUT; use `-o FILE` to write a file.

See [usage](docs/usage.md) for version listing, custom manifests, encoding, metadata and blocked strings. Option help is available with `auto --help` or `manual --help`.

### Migration

The Java Edition shell entry points have been replaced by `generator.py`:

| Previous script | Python command |
| --- | --- |
| `generator-zh` | `python3 generator.py -o result.lua auto en_us zh_cn zh_tw zh_hk` |
| `generator-lzh` | `python3 generator.py -o result.lua auto en_us lzh` |
| `generator-zh_manualsource` | `python3 generator.py -o result.lua manual en_us.json zh_cn.json zh_tw.json zh_hk.json` |
| `generator-lzh_manualsource` | `python3 generator.py -o result.lua manual en_us.json lzh.json` |

## .lang converter

`lang2json.py` converts selected `.lang` files into one language JSON. List files from highest to lowest priority: `vanilla` first, then supplementary files that fill missing keys. The first file's value wins conflicts. It uses Python 3.10+ and its standard library. Convert each language, then use `generator.py manual` to produce Lua.

```sh
python3 lang2json.py                              # show help
python3 lang2json.py -o en_US.json vanilla.lang extra.lang
python3 lang2json.py -t -o en_US.json vanilla.lang extra.lang
python3 generator.py -o names.lua manual en_US.json zh_CN.json zh_TW.json
```

Every conversion removes trailing ordinary spaces (U+0020) and no-break spaces (NBSP, U+00A0) from values; leading and interior whitespace is retained. In `resourcePack.editor.customMeshTool.label.meshInfoValue`, literal `\n` sequences become actual line breaks, with or without `-t`; other backslash sequences are preserved. Ordinary conversion preserves format characters. `-t, --translate-parser` prepares original Bedrock values once: it adapts single-digit bare indices and integer markers, and escapes literal percent signs, including consecutive percents, floating-point text and URL encodings. Literal suffixes and parameter order are retained.

See [converter usage](docs/lang2json.md) for options, comment and merge rules, the format conversion table and file-order examples. Convert each language separately before running `generator.py manual`.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

See [test instructions](tests/README.md) for dependencies and official-data checks.

## License

CC0 1.0 Universal; see [LICENSE](LICENSE).
