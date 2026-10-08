# NameProvider Data Generator

Generate Lua data for the [NameProvider module](https://zh.minecraft.wiki/w/Module:NameProvider).

## Java Edition

Requires Python 3.10+ and only its standard library. Output is compatible with Lua 5.1.

```sh
python3 generator.py                              # show help
python3 generator.py auto en_us zh_cn zh_tw zh_hk  # latest version
python3 generator.py auto -v 1.21.8 en_us lzh       # specified version
python3 generator.py -o names.lua manual en_us.json lzh.json
```

Languages or files set the output column order. The first input supplies the
keys and fallback translations. Output defaults to UTF-8 STDOUT; use `-o FILE`
to write a file.

See [usage](docs/usage.md) for version listing, custom manifests, encoding,
metadata and blocked strings. Option help is available with `auto --help` or
`manual --help`.

### Migration

The Java Edition shell entry points have been replaced by `generator.py`:

| Previous script | Python command |
| --- | --- |
| `generator-zh` | `python3 generator.py -o result.lua auto en_us zh_cn zh_tw zh_hk` |
| `generator-lzh` | `python3 generator.py -o result.lua auto en_us lzh` |
| `generator-zh_manualsource` | `python3 generator.py -o result.lua manual en_us.json zh_cn.json zh_tw.json zh_hk.json` |
| `generator-lzh_manualsource` | `python3 generator.py -o result.lua manual en_us.json lzh.json` |

## Tests

```sh
python3 -m unittest discover -s tests -v
```

See [test instructions](tests/README.md) for dependencies and official-data checks.

## Bedrock Edition

`generatorBE_lite` reads `en_US.lang`, `zh_CN.lang` and `zh_TW.lang` from the
working directory and excludes strings containing `%`. It requires Linux,
`dos2unix` and the text-processing utilities.

```sh
./generatorBE_lite
```

## License

CC0 1.0 Universal; see [LICENSE](LICENSE).
