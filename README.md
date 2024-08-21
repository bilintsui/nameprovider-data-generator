# NameProvider Data Generator
This is a simple data generator to generate data for [NameProvider module](https://zh.minecraft.wiki/w/Module:NameProvider).

## Dependency
* `curl`
* `unzip`
* `JSON` perl module

## Usage
`./generator <version_manifest_url> [manual_version]`
* <version_manifest_url>

	URL of a qualified version manifest. Usually fine to use the official one.

	Official: https://piston-meta.mojang.com/mc/game/version_manifest.json
* [manual_version]

	Optional, the exact game version used to generate data. Defaults to 0.

	Number based on the order of versions in the file provided, start with 0.
## Output
* A qualified "output-*version*.txt", which located in the current working directory.

## License
This script is licensed with CC0 1.0 Universal, see full text in `LICENSE`.
