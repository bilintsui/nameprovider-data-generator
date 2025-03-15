# NameProvider Data Generator
This is a simple data generator to generate data for [NameProvider module](https://zh.minecraft.wiki/w/Module:NameProvider).

**Currently, generator for Bedrock Edition (`generatorBE_lite`) only outputs strings without `%`, it will supported in future.**

## Dependency
* Linux
* `curl`
* `jq`
* `unzip`
* `dos2unix` (for `generatorBE_lite`)

## Usage
`./generator-*` or `./generatorBE_lite`

Note that `generatorBE_lite` requires `en_US.lang`, `zh_CN.lang`, and 'zh_TW.lang' from Bedrock Edition packages in the working directory.

## Output
* A qualified Lua data table "result.lua", which located in the current working directory.

## License
This script is licensed with CC0 1.0 Universal, see full text in `LICENSE`.
