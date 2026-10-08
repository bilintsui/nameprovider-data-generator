# Tests

Run the commands below from the repository root with Python 3.10+.

Lua execution checks use a Lua 5.1 shared library. On Debian or Ubuntu, install
the system library with:

```sh
sudo apt-get update
sudo apt-get install --no-install-recommends -y liblua5.1-0
```

Unit tests skip Lua execution checks when the library is unavailable; the
official-data checker requires it. `NAMEPROVIDER_LUA_LIBRARY` can select a
custom library path. The adapter verifies that `_VERSION` is `Lua 5.1`.
GNU `sort` enables the optional randomized version-order check. The HTTP test
needs permission to bind a temporary server to `127.0.0.1`.

## Regression suite

```sh
python3 -m unittest discover -s tests -v
```

Covers CLI behavior, local and HTTP sources, version selection, column order,
keys and fallback, blocked strings, metadata, encodings, Lua string round-trips
and the fixed output fixtures under `tests/fixtures/`.

## Official data

```sh
python3 tests/check_official_data.py --cache /tmp/nameprovider-reference
```

Downloads `latest`, `1.21.8` and `1.13`, verifies asset hashes, compares auto and
manual output with matching metadata, and checks each output value in Lua 5.1
against its source. Languages include Gothic, Arabic-script Malay, Kannada,
Lao, Yiddish and other scripts with supplementary or combining characters.

Use `--versions` to select versions or `--manifest` to use a saved manifest.
Omit `--cache` to discard downloads after the check. A cache retains its
manifest; remove `manifest.json` to refresh the available versions.
