# NameProvider Data Generator
This is a simple simple data generator for generating data of [NameProvider module](https://minecraft.fandom.com/zh/wiki/Module:NameProvider).

## Dependency
* `curl`
* `unzip`
* `JSON` perl module

## Usage
`./generator <version_manifest_url>`
* <version_manifest_url>: URL of a version manifest. It's fine to use https://piston-meta.mojang.com/mc/game/version_manifest.json usually.

## Output
* A qualified "output.txt", which located in the current working directory.

## License
This script is licensed with CC0 1.0 Univsersal, see full text in `LICENSE`.
